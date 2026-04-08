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
    # نعمل فقط عند التسليم
    if instance.status == Order.Status.DELIVERED:
        customer = instance.customer
        inviter = customer.invited_by
        
        if inviter:
            settings = SiteSetting.objects.first()
            reward = settings.referral_reward_amount if settings else Decimal('50.00')
            limit = settings.referral_reward_limit_orders if settings else 1
            
            # 1. نحسب عدد الطلبات المكتملة لهذا العميل
            completed_orders_count = Order.objects.filter(
                customer=customer, 
                status=Order.Status.DELIVERED
            ).count()
            
            # 2. هل تجاوزنا الحد؟
            # (نستخدم <= لأن الطلب الحالي تم عده في completed_orders_count)
            if completed_orders_count <= limit:
                
                # هل تم منح المكافأة لهذا الطلب تحديداً من قبل؟ (منع التكرار)
                # يمكننا استخدام وصف Notification كعلامة، أو إضافة حقل is_rewarded في Order
                # الحل الأسهل: Notification
                already_rewarded = Notification.objects.filter(
                    recipient=inviter, 
                    message__contains=f"الطلب #{instance.order_id}"
                ).exists()
                
                if not already_rewarded:
                    inviter.referral_balance += reward
                    inviter.save()
                    
                    Notification.objects.create(
                        recipient=inviter, 
                        title="مكافأة دعوة! 💰", 
                        message=f"حصلت على {reward} ج.م بفضل الطلب #{instance.order_id} لصديقك {customer.first_name}."
                    )
            # مكافأة للمستخدم الجديد (اختياري، لو عايز تديله رصيد هو كمان)
            # customer.referral_balance += reward
            # customer.save()
# ========================================================
# 3. النظام المالي (الحاسم) 💸
# ========================================================
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
# تأكد من استدعاء الموديلات الصحيحة مثل Order, Wallet, WalletTransaction في أعلى الملف

@receiver(post_save, sender=Order)
def distribute_profits(sender, instance, created, **kwargs):
    # العمل فقط عند التسليم النهائي
    if instance.status == Order.Status.DELIVERED:
        
        # 1. حماية ذكية من التكرار (تتجاهل عملية خصم العمولة)
        # نبحث فقط عن العمليات المعلقة (PENDING) أو التعويضات (COMPENSATION) الخاصة بهذا الطلب
        already_paid = WalletTransaction.objects.filter(
            description__contains=f"#{instance.order_id}",
            transaction_type__in=['PENDING', 'COMPENSATION'] # نتجاهل SALE الخاص بخصم العمولة
        ).exists()
        
        if already_paid:
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
            recorded_price = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            
            # ب. خصم الدعوة (Referral)
            ref_discount = getattr(item, 'referral_discount', Decimal('0.00'))

            # ج. السعر الفعلي الذي دفعه العميل من جيبه للمنتج
            customer_paid_total = (recorded_price * qty) - ref_discount
            if customer_paid_total < 0: customer_paid_total = Decimal('0.00')

            # د. تعويض "عرض المنصة" (Platform Offer)
            offer_compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_platform_offer and offer.is_active and recorded_price < base_price:
                    offer_compensation = (base_price - recorded_price) * qty
            except:
                pass

            # هـ. إجمالي التعويضات المستحقة للتاجر عن هذا المنتج
            total_item_compensation = offer_compensation + ref_discount

            merchant_earnings[merchant]['product_revenue'] += customer_paid_total
            merchant_earnings[merchant]['compensation'] += total_item_compensation

        # --- [الجديد] إضافة تعويض "قسيمة الإدارة المخصصة" للتاجر صاحب هذا الطلب ---
        if hasattr(instance, 'admin_discount') and instance.admin_discount and instance.admin_discount > 0:
            if instance.merchant in merchant_earnings:
                merchant_earnings[instance.merchant]['compensation'] += Decimal(str(instance.admin_discount))
        # --------------------------------------------------------------------------

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
                is_shipping_compensated = False

                # نتأكد أن التاجر هو صاحب الطلب
                if instance.merchant == merchant:
                    if instance.shipping_cost > 0:
                        # العميل دفع الشحن -> هذا دخل للتاجر
                        shipping_income = instance.shipping_cost
                        shipping_desc = "شحن مدفوع"
                    else:
                        # الشحن مجاني (0) -> من يتحمل التكلفة؟
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
                        
                        # حساب قيمة الشحن الأصلية لتعويض التاجر
                        rate_obj = MerchantShippingRate.objects.filter(
                            merchant=merchant, governorate=instance.governorate
                        ).first()
                        orig_ship = rate_obj.rate if rate_obj else Decimal('50.00')

                        if is_platform_funded:
                            shipping_income = orig_ship
                            shipping_desc = "تعويض شحن (عرض منصة)"
                            is_shipping_compensated = True
                        
                        elif instance.is_first_order:
                            shipping_income = orig_ship
                            shipping_desc = "تعويض شحن (أول طلب)"
                            is_shipping_compensated = True
                        
                        # --- [الجديد] تعويض الشحن إذا كان بسبب قسيمة الإدارة ---
                        elif hasattr(instance, 'admin_discount') and instance.admin_discount > 0:
                            shipping_income = orig_ship
                            shipping_desc = "تعويض شحن (قسيمة الإدارة)"
                            is_shipping_compensated = True
                        # -------------------------------------------------------

                        else:
                            # عرض تاجر -> التاجر يتحمل التكلفة
                            shipping_income = Decimal('0.00')
                            shipping_desc = "شحن مجاني (عرض متجرك)"

                # --- الإضافة للمحفظة ---
                
                # صياغة وصف احترافي للتاجر
                extra_desc = f" | {shipping_desc}" if shipping_desc else ""
                if comp > 0:
                    extra_desc += f" | يشمل تعويضات {comp} ج.م"

                # فحص طريقة الدفع (أونلاين أو محفظة = دفع إلكتروني)
                payment_method_str = str(instance.payment_method).upper()
                is_electronic = payment_method_str in ['ONLINE', 'WALLET']

                if is_electronic:
                    # حالة الدفع الإلكتروني: التاجر لم يستلم شيء -> نضيف له كل المستحقات
                    total_deposit = prod_rev + shipping_income + comp
                    
                    if total_deposit > 0:
                        wallet.pending_balance += total_deposit
                        
                        tx = WalletTransaction(
                            wallet=wallet, 
                            amount=total_deposit,
                            transaction_type='PENDING',
                            description=f"مستحقات طلب إلكتروني #{instance.order_id}{extra_desc}",
                            balance_after=wallet.balance, 
                            is_released=False
                        )
                        # محاولة ربط الطلب إذا كان الحقل موجوداً في الموديل
                        if hasattr(tx, 'related_order_id'):
                            tx.related_order_id = instance.order_id
                        tx.save()

                else:
                    # حالة الدفع كاش (COD): التاجر استلم ثمن المنتج والشحن من العميل مباشرة
                    # نضيف له فقط التعويضات والشحن المعوض من المنصة
                    total_comp_only = comp
                    
                    if is_shipping_compensated:
                        total_comp_only += shipping_income
                    
                    if total_comp_only > 0:
                        wallet.pending_balance += total_comp_only
                        
                        tx = WalletTransaction(
                            wallet=wallet, 
                            amount=total_comp_only,
                            # استخدام COMPENSATION لو موجودة، أو PENDING
                            transaction_type=getattr(WalletTransaction.TxType, 'COMPENSATION', 'COMPENSATION'),
                            description=f"تعويضات طلب كاش #{instance.order_id}{extra_desc}",
                            balance_after=wallet.balance, 
                            is_released=False
                        )
                        if hasattr(tx, 'related_order_id'):
                            tx.related_order_id = instance.order_id
                        tx.save()

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



