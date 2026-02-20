from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from .models import Order, OrderItem, ProductSize, Wallet, WalletTransaction, DepositRequest,MerchantShippingRate

# 1. تحديث إجمالي الطلب (للعرض فقط)
@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def update_order_totals(sender, instance, **kwargs):
    order = instance.order
    # (نحسب المجموع فقط للعرض، ولا نضيف رسوم هنا لأنها تضاف في Checkout)
    current_items = order.items.all()
    # ✅ الصحيح: نضرب السعر في الكمية
    total_products = sum(item.quantity * item.price_at_purchase for item in current_items)
    order.total_products_price = total_products
    order.final_total = total_products + order.shipping_cost + order.platform_fees
    order.save(update_fields=['total_products_price', 'final_total'])

# 2. إدارة المخزون (خصم الكميات عند الشراء)
@receiver(post_save, sender=Order)
def manage_inventory(sender, instance, created, **kwargs):
    if created: return
    
    # عند تحول الطلب لـ PENDING (أي تم تأكيده والدفع)
    if instance.status == Order.Status.PENDING:
        for item in instance.items.all():
            ProductSize.objects.filter(pk=item.product_size.pk).update(
                stock_quantity=F('stock_quantity') - item.quantity
            )
    
    # عند الإلغاء، نعيد الكمية
    elif instance.status == Order.Status.CANCELLED:
        for item in instance.items.all():
            ProductSize.objects.filter(pk=item.product_size.pk).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )

# ========================================================
# 3. النظام المالي (الحاسم) 💸
# ========================================================
@receiver(post_save, sender=Order)
def distribute_profits(sender, instance, created, **kwargs):
    # العمل فقط عند التسليم النهائي
    if instance.status == Order.Status.DELIVERED:
        
        # حماية من التكرار
        if WalletTransaction.objects.filter(related_order_id=instance.order_id).exists():
            return

        merchant_earnings = {}

        # 1. تجميع أرباح المنتجات
        for item in instance.items.all():
            merchant = item.product_size.product.merchant
            if not merchant: continue

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = {
                    'revenue': Decimal('0.00'), 
                    'compensation': Decimal('0.00'),
                    'commission': Decimal('0.00')
                }
            
            # أ. الأسعار
            price_paid = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            
            # ب. تعويض العروض (Platform Offer)
            compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                # إذا كان العرض من المنصة والسعر المدفوع أقل من الأصلي
                if offer and offer.is_platform_offer and offer.is_active and price_paid < base_price:
                    compensation = (base_price - price_paid) * qty
            except:
                pass

            # ج. خصم عمولة المنصة
            # (السعر * النسبة / 100) * الكمية
            pct = item.product_size.product.commission_pct / 100
            commission = (price_paid * pct * qty) # العمولة تحسب على سعر البيع الفعلي

            # د. تجميع البيانات
            # الإيراد = ما دفعه العميل
            merchant_earnings[merchant]['revenue'] += (price_paid * qty)
            # التعويض = ما ستدفعه المنصة
            merchant_earnings[merchant]['compensation'] += compensation
            # العمولة = ما ستخصمه المنصة
            merchant_earnings[merchant]['commission'] += commission

        # 2. التنفيذ وإضافة الشحن
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                # هـ. حساب الشحن
                shipping_income = Decimal('0.00')
                
                # نتأكد أن هذا التاجر هو صاحب الطلب (لأنه هو من شحن)
                if instance.merchant == merchant:
                    
                    # 1. حساب قيمة الشحن الأصلية (للمقارنة)
                    rate_obj = MerchantShippingRate.objects.filter(
                        merchant=merchant, governorate=instance.governorate
                    ).first()
                    original_shipping = rate_obj.rate if rate_obj else Decimal('50.00')

                    # 2. فحص من يتحمل الشحن؟
                    if instance.shipping_cost > 0:
                        # العميل دفع الشحن -> التاجر يأخذه
                        shipping_income = instance.shipping_cost
                    
                    else:
                        # الشحن مجاني (0) -> من يدفع؟
                        
                        # أ. هل هو عرض منصة (Platform Free Shipping)؟
                        is_platform_funded = False
                        for item in instance.items.all():
                            try:
                                offer = item.product_size.product.active_offer
                                if offer and offer.is_platform_offer and offer.free_shipping:
                                    if item.quantity >= offer.free_shipping_threshold:
                                        is_platform_funded = True
                                        break
                            except: pass
                        
                        if is_platform_funded:
                            # المنصة تعوض
                            shipping_income = original_shipping
                            WalletTransaction.objects.create(
                                wallet=wallet, amount=original_shipping,
                                transaction_type=WalletTransaction.TxType.COMPENSATION,
                                related_order_id=instance.order_id,
                                description=f"تعويض شحن (عرض منصة)",
                                balance_after=wallet.balance, is_released=False
                            )
                        
                        elif instance.is_first_order:
                            # أول طلب (المنصة تعوض)
                            shipping_income = original_shipping
                            WalletTransaction.objects.create(
                                wallet=wallet, amount=original_shipping,
                                transaction_type=WalletTransaction.TxType.COMPENSATION,
                                related_order_id=instance.order_id,
                                description=f"تعويض شحن (أول طلب)",
                                balance_after=wallet.balance, is_released=False
                            )
                        
                        else:
                            # عرض تاجر -> لا تعويض (التاجر يتحمل)
                            shipping_income = 0

                # و. تحديد المبلغ النهائي للإيداع
                # إذا كاش: نضيف (التعويضات + الشحن المعوض فقط) - العميل دفع المنتج بيده
                # إذا أونلاين: نضيف (إيراد المنتج + التعويضات + الشحن)
                
                amount_to_deposit = Decimal('0.00')
                
                if instance.payment_method == Order.PaymentMethod.ONLINE:
                    amount_to_deposit = data['revenue'] + data['compensation'] + shipping_income
                else:
                    # في الكاش، التاجر أخذ الإيراد والشحن من العميل بيده
                    # لذا نضيف له "التعويضات" فقط
                    amount_to_deposit = data['compensation'] 
                    # إذا كان الشحن "معوضاً" (دخل في shipping_income أعلاه)، نضيفه
                    # لكن shipping_income يحتوي على (ما دفعه العميل + ما دفعته المنصة)
                    # نحتاج فقط لما دفعته المنصة
                    if shipping_income > 0 and instance.shipping_cost == 0:
                        amount_to_deposit += shipping_income

                # ز. الإضافة للرصيد المعلق (Pending)
                if amount_to_deposit > 0:
                    wallet.pending_balance += amount_to_deposit
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=amount_to_deposit,
                        transaction_type='PENDING',
                        related_order_id=instance.order_id,
                        description=f"مستحقات طلب #{instance.order_id} ({instance.get_payment_method_display()})",
                        balance_after=wallet.balance, is_released=False
                    )

                # ح. خصم العمولة (دائماً تخصم من المتاح فوراً)
                commission = data['commission']
                if commission > 0:
                    wallet.balance -= commission
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=-commission,
                        transaction_type=WalletTransaction.TxType.SALE,
                        related_order_id=instance.order_id,
                        description=f"خصم عمولة المنصة ({instance.payment_method})",
                        balance_after=wallet.balance, is_released=True
                    )
                
                wallet.save()
# 4. معالجة طلبات شحن الرصيد (الإيداع)
@receiver(post_save, sender=DepositRequest)
def process_deposit(sender, instance, **kwargs):
    if instance.status == DepositRequest.Status.APPROVED:
        desc = f"شحن رصيد (طلب #{instance.id})"
        if WalletTransaction.objects.filter(description=desc).exists(): return

        with transaction.atomic():
            wallet = instance.merchant.wallet
            wallet.balance += instance.amount # الإيداع ينزل في المتاح فوراً
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet,
                amount=instance.amount,
                transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=desc,
                balance_after=wallet.balance
            )