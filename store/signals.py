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

        # 1. تجميع أرباح المنتجات لكل تاجر
        for item in instance.items.all():
            merchant = item.product_size.product.merchant
            if not merchant: continue

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = {
                    'product_revenue': Decimal('0.00'), # سعر البيع الفعلي
                    'compensation': Decimal('0.00'),    # تعويض فرق السعر (عروض)
                }
            
            # أ. الأسعار
            price_paid = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            
            # ب. التعويض عن العروض (Platform Offer Compensation)
            compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                # إذا كان العرض من المنصة والسعر المدفوع أقل من الأصلي -> نعوض الفرق
                if offer and offer.is_platform_offer and offer.is_active and price_paid < base_price:
                    compensation = (base_price - price_paid) * qty
            except:
                pass

            # ج. تجميع البيانات
            merchant_earnings[merchant]['product_revenue'] += (price_paid * qty)
            merchant_earnings[merchant]['compensation'] += compensation

        # 2. التنفيذ الفعلي
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                product_revenue = data['product_revenue']
                compensation = data['compensation']
                
                shipping_income = Decimal('0.00')
                shipping_desc = ""
                is_shipping_compensated = False

                # د. حساب الشحن (إذا كان التاجر هو صاحب الطلب)
                if instance.merchant == merchant:
                    
                    # 1. شحن مدفوع (العميل دفعه)
                    if instance.shipping_cost > 0:
                        shipping_income = instance.shipping_cost
                        shipping_desc = f"شحن مدفوع (طلب #{instance.order_id})"
                    
                    # 2. شحن مجاني (0) -> من يدفع؟
                    else:
                        # أ. هل هو عرض منصة؟
                        is_platform_funded = False
                        for item in instance.items.all():
                            try:
                                offer = item.product_size.product.active_offer
                                if offer and offer.is_platform_offer and offer.free_shipping:
                                    if item.quantity >= offer.free_shipping_threshold:
                                        is_platform_funded = True
                                        break
                            except: pass
                        
                        # حساب السعر الأصلي للشحن (للتعويض)
                        rate_obj = MerchantShippingRate.objects.filter(
                            merchant=merchant, governorate=instance.governorate
                        ).first()
                        original_shipping = rate_obj.rate if rate_obj else Decimal('50.00')

                        if is_platform_funded:
                            shipping_income = original_shipping
                            shipping_desc = f"تعويض شحن (عرض منصة)"
                            is_shipping_compensated = True
                        
                        elif instance.is_first_order:
                            shipping_income = original_shipping
                            shipping_desc = f"تعويض شحن (أول طلب)"
                            is_shipping_compensated = True
                        
                        else:
                            # عرض تاجر -> لا دخل (التاجر يتحمل)
                            shipping_income = 0

                # ==========================================
                # هـ. الإضافة للمحفظة (اللوجيك الحاسم)
                # ==========================================
                
                # 1. حالة الدفع أونلاين (ONLINE)
                # التاجر لم يستلم شيئاً بيده -> المنصة تحول له كل شيء
                if instance.payment_method == Order.PaymentMethod.ONLINE:
                    
                    # أ. سعر المنتجات
                    if product_revenue > 0:
                        wallet.pending_balance += product_revenue
                        WalletTransaction.objects.create(
                            wallet=wallet, amount=product_revenue,
                            transaction_type='PENDING',
                            description=f"مبيعات منتجات (أونلاين #{instance.order_id})",
                            balance_after=wallet.balance, is_released=False
                        )
                    
                    # ب. الشحن (سواء دفعه العميل أو تعويض)
                    if shipping_income > 0:
                        wallet.pending_balance += shipping_income
                        WalletTransaction.objects.create(
                            wallet=wallet, amount=shipping_income,
                            transaction_type='PENDING',
                            description=shipping_desc,
                            balance_after=wallet.balance, is_released=False
                        )

                # 2. حالة الدفع كاش (COD)
                # التاجر استلم (سعر المنتج + الشحن المدفوع) في يده
                # -> المنصة لا تضيف له هذا المبلغ، بل تضيف "التعويضات" فقط
                else:
                    # أ. هل الشحن كان تعويضاً؟ (مجاني للعميل، مدفوع من المنصة)
                    if is_shipping_compensated and shipping_income > 0:
                        wallet.pending_balance += shipping_income
                        WalletTransaction.objects.create(
                            wallet=wallet, amount=shipping_income,
                            transaction_type=WalletTransaction.TxType.COMPENSATION,
                            description=shipping_desc,
                            balance_after=wallet.balance, is_released=False
                        )
                    
                    # (لاحظ: لا نضيف product_revenue ولا شحن العميل المدفوع)

                # 3. إضافة تعويضات العروض (دائماً تضاف لأنها من المنصة)
                if compensation > 0:
                    wallet.pending_balance += compensation
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=compensation,
                        transaction_type=WalletTransaction.TxType.COMPENSATION,
                        description=f"تعويض فرق عرض (طلب #{instance.order_id})",
                        balance_after=wallet.balance, is_released=False
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