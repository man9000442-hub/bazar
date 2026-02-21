from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from .models import Order, OrderItem, ProductSize, Wallet, WalletTransaction, DepositRequest,MerchantShippingRate,Notification,SiteSetting

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
@receiver(post_save, sender=Order)
def apply_referral_reward(sender, instance, created, **kwargs):
    if instance.status == Order.Status.DELIVERED and instance.is_first_order:
        customer = instance.customer
        inviter = customer.invited_by
        
        if inviter:
            settings = SiteSetting.objects.first()
            reward = settings.referral_reward_amount if settings else Decimal('50.00')
            
            # مكافأة لصاحب الكود
            inviter.referral_balance += reward
            inviter.save()
            Notification.objects.create(recipient=inviter, title="مكافأة جديدة! 💰", message=f"حصلت على {reward} ج.م لأن {customer.first_name} أتم أول طلب.")
            
            # مكافأة للمستخدم الجديد (اختياري، لو عايز تديله رصيد هو كمان)
            # customer.referral_balance += reward
            # customer.save()
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

        # ==========================================
        # 1. تجميع الأرباح والتعويضات لكل تاجر
        # ==========================================
        for item in instance.items.all():
            merchant = item.product_size.product.merchant
            if not merchant: continue

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = {
                    'product_revenue': Decimal('0.00'), # ما دفعه العميل للمنتج
                    'compensation': Decimal('0.00'),    # ما ستدفعه المنصة (عروض + دعوات)
                }
            
            # أ. الأسعار الأساسية
            # السعر المسجل في الطلب (قد يكون مخفضاً بسبب عرض)
            recorded_price = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            # السعر الأصلي للمنتج (بدون أي خصم)
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            
            # ب. خصم الدعوة (Referral)
            # هذا الخصم تتحمله المنصة بالكامل
            ref_discount = getattr(item, 'referral_discount', Decimal('0.00'))

            # ج. السعر الفعلي الذي دفعه العميل من جيبه
            # (السعر المسجل * الكمية) - خصم الدعوة
            customer_paid_total = (recorded_price * qty) - ref_discount
            if customer_paid_total < 0: customer_paid_total = 0

            # د. تعويض "عرض المنصة" (Platform Offer)
            # إذا كان السعر المسجل أقل من الأصلي، وكان السبب عرض منصة -> نعوض الفرق
            offer_compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_platform_offer and offer.is_active and recorded_price < base_price:
                    offer_compensation = (base_price - recorded_price) * qty
            except:
                pass

            # هـ. إجمالي التعويضات المستحقة للتاجر عن هذا المنتج
            # (تعويض عرض المنصة + تعويض خصم الدعوة)
            total_item_compensation = offer_compensation + ref_discount

            # و. التجميع في القاموس
            merchant_earnings[merchant]['product_revenue'] += customer_paid_total
            merchant_earnings[merchant]['compensation'] += total_item_compensation

        # ==========================================
        # 2. التنفيذ المالي (المحفظة)
        # ==========================================
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                prod_rev = data['product_revenue']
                comp = data['compensation']
                
                # --- حساب الشحن (من يدفعه؟) ---
                shipping_income = Decimal('0.00')
                shipping_desc = ""
                is_shipping_compensated = False # هل المنصة هي من دفعت الشحن؟

                # نتأكد أن التاجر هو صاحب الطلب
                if instance.merchant == merchant:
                    if instance.shipping_cost > 0:
                        # العميل دفع الشحن -> هذا دخل للتاجر
                        shipping_income = instance.shipping_cost
                        shipping_desc = f"شحن مدفوع (طلب #{instance.order_id})"
                    else:
                        # الشحن مجاني (0) -> من يتحمل؟
                        is_platform_funded = False
                        
                        # فحص هل هو عرض منصة؟
                        for item in instance.items.all():
                            try:
                                offer = item.product_size.product.active_offer
                                if offer and offer.is_platform_offer and offer.free_shipping:
                                    if item.quantity >= offer.free_shipping_threshold:
                                        is_platform_funded = True
                                        break
                            except: pass
                        
                        # حساب قيمة الشحن الأصلية للتعويض
                        rate_obj = MerchantShippingRate.objects.filter(
                            merchant=merchant, governorate=instance.governorate
                        ).first()
                        orig_ship = rate_obj.rate if rate_obj else Decimal('50.00')

                        if is_platform_funded:
                            shipping_income = orig_ship
                            shipping_desc = f"تعويض شحن (عرض منصة)"
                            is_shipping_compensated = True
                        
                        elif instance.is_first_order:
                            shipping_income = orig_ship
                            shipping_desc = f"تعويض شحن (أول طلب)"
                            is_shipping_compensated = True
                        
                        else:
                            # عرض تاجر -> لا دخل (التاجر يتحمل)
                            shipping_income = 0

                # --- الإضافة للمحفظة ---
                
                # 1. حالة الدفع أونلاين (ONLINE)
                # التاجر لم يستلم شيئاً بيده -> نضيف له كل المستحقات
                if instance.payment_method == Order.PaymentMethod.ONLINE:
                    # المستحقات = (سعر المنتجات + الشحن + التعويضات)
                    total_deposit = prod_rev + shipping_income + comp
                    
                    if total_deposit > 0:
                        wallet.pending_balance += total_deposit
                        WalletTransaction.objects.create(
                            wallet=wallet, amount=total_deposit,
                            transaction_type='PENDING',
                            description=f"مستحقات طلب أونلاين #{instance.order_id}",
                            balance_after=wallet.balance, is_released=False
                        )

                # 2. حالة الدفع كاش (COD)
                # التاجر استلم (سعر المنتجات + الشحن المدفوع) في يده
                # -> نضيف له فقط (التعويضات + الشحن المعوض من المنصة)
                else:
                    total_comp_only = comp
                    
                    if is_shipping_compensated:
                        total_comp_only += shipping_income
                        # (ملاحظة: إذا كان الشحن مدفوعاً، التاجر أخذه بيده، فلا نضيفه هنا)
                    
                    if total_comp_only > 0:
                        wallet.pending_balance += total_comp_only
                        WalletTransaction.objects.create(
                            wallet=wallet, amount=total_comp_only,
                            transaction_type=WalletTransaction.TxType.COMPENSATION,
                            description=f"تعويضات طلب كاش #{instance.order_id}",
                            balance_after=wallet.balance, is_released=False
                        )

                # --- (العمولة تم خصمها مسبقاً عند الشحن، فلا نخصمها هنا) ---
                
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



