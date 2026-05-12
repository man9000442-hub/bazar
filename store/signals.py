from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from .models import Order, OrderItem, ProductSize, Wallet, WalletTransaction, DepositRequest, MerchantShippingRate, Notification, SiteSetting

# 1. تحديث إجمالي الطلب (للعرض فقط)
@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def update_order_totals(sender, instance, **kwargs):
    order = instance.order
    current_items = order.items.all()
    total_products = sum(item.quantity * item.price_at_purchase for item in current_items)
    order.total_products_price = total_products
    order.final_total = total_products + order.shipping_cost + order.platform_fees
    order.save(update_fields=['total_products_price', 'final_total'])

# 2. إدارة المخزون (خصم الكميات عند الشراء)
@receiver(post_save, sender=Order)
def manage_inventory(sender, instance, created, **kwargs):
    if created: return
    if instance.status == Order.Status.PENDING:
        for item in instance.items.all():
            ProductSize.objects.filter(pk=item.product_size.pk).update(
                stock_quantity=F('stock_quantity') - item.quantity
            )
    elif instance.status == Order.Status.CANCELLED:
        for item in instance.items.all():
            ProductSize.objects.filter(pk=item.product_size.pk).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )

from datetime import timedelta
from django.utils import timezone
from accounts.models import ReferralRewardLog # استدعاء السجل

@receiver(post_save, sender=Order)
def apply_referral_reward(sender, instance, created, **kwargs):
    if instance.status == Order.Status.DELIVERED:
        customer = instance.customer
        inviter = customer.invited_by
        
        if inviter:
            # تنظيف أي أرصدة منتهية للداعي قبل إضافة الرصيد الجديد
            inviter.clear_expired_referrals()
            
            settings = SiteSetting.get_settings(instance.country)
            
            # جلب الإعدادات المخصصة للدولة
            reward_pct = settings.referral_reward_percentage if settings else Decimal('10.00')
            validity_days = settings.referral_reward_validity_days if settings else 30
            limit = settings.referral_reward_limit_orders if settings else 3 # بناءً على طلبك (مثلاً أول 3 طلبات)
            
            completed_orders_count = Order.objects.filter(
                customer=customer, status=Order.Status.DELIVERED
            ).count()
            
            if completed_orders_count <= limit:
                already_rewarded = Notification.objects.filter(
                    recipient=inviter, message__contains=f"الطلب #{instance.order_id}"
                ).exists()
                
                if not already_rewarded:
                    max_reward_amount = settings.referral_reward_max_amount if settings else Decimal('100.00')
                    calculated_reward = (instance.total_products_price * reward_pct) / Decimal('100.00')
                    reward_amount = min(calculated_reward, max_reward_amount)
                    
                    if reward_amount > 0:
                        expires_time = timezone.now() + timedelta(days=validity_days)
                        
                        with transaction.atomic():
                            from accounts.models import User
                            locked_inviter = User.objects.select_for_update().get(id=inviter.id)
                            locked_inviter.referral_balance += reward_amount
                            locked_inviter.save()
                            
                            # تسجيل المعاملة لتتبع انتهاء الصلاحية لاحقاً
                            ReferralRewardLog.objects.create(
                                user=locked_inviter,
                                amount=reward_amount,
                                order_id=instance.order_id,
                                expires_at=expires_time
                            )
                        
                        Notification.objects.create(
                            recipient=inviter, title="مكافأة دعوة جديدة! 🎁", 
                            message=f"حصلت على نسبة {reward_pct}% ({round(reward_amount, 2)} ج.م) بفضل الطلب #{instance.order_id} لصديقك {customer.first_name}. رصيدك صالح للاستخدام لمدة {validity_days} يوم."
                        )
                        
# ========================================================
# 3. النظام المالي (الحاسم) 💸
# ========================================================
# ========================================================
# 3. النظام المالي (توزيع الأرباح وخصم عمولات فواتيرك) 💸
# ========================================================
@receiver(post_save, sender=Order)
def distribute_profits(sender, instance, created, **kwargs):
    if instance.status == Order.Status.DELIVERED:
        already_paid = WalletTransaction.objects.filter(
            description__contains=f"#{instance.order_id}",
            transaction_type__in=['PENDING', 'COMPENSATION'] 
        ).exists()
        
        if already_paid: return

        merchant_earnings = {}

        for item in instance.items.all():
            merchant = item.product_size.product.merchant
            if not merchant: continue

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = {'product_revenue': Decimal('0.00'), 'compensation': Decimal('0.00')}
            
            recorded_price = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            ref_discount = getattr(item, 'referral_discount', Decimal('0.00'))

            customer_paid_total = (recorded_price * qty) - ref_discount
            if customer_paid_total < 0: customer_paid_total = Decimal('0.00')

            offer_compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_platform_offer and offer.is_active and recorded_price < base_price:
                    offer_compensation = (base_price - recorded_price) * qty
            except: pass

            total_item_compensation = offer_compensation + ref_discount

            merchant_earnings[merchant]['product_revenue'] += customer_paid_total
            merchant_earnings[merchant]['compensation'] += total_item_compensation

        if hasattr(instance, 'admin_discount') and instance.admin_discount and instance.admin_discount > 0:
            if instance.merchant in merchant_earnings:
                merchant_earnings[instance.merchant]['compensation'] += Decimal(str(instance.admin_discount))

        # 🔥 حساب رسوم بوابة الدفع (فواتيرك فقط) بناءً على إعدادات الدولة
        gateway_fees_deduction = Decimal('0.00')
        is_electronic = str(instance.payment_method).upper() in ['ONLINE', 'WALLET']
        gateway_name = "Fawaterk" # تم توحيد البوابة
        
        if is_electronic and instance.country:
            # نجلب الإعدادات المخصصة للدولة لحساب رسوم فواتيرك
            site_settings = SiteSetting.get_settings(country=instance.country)
            
            pct_fee = (instance.final_total * site_settings.fawaterk_fee_percentage) / Decimal('100.00')
            fixed_fee = site_settings.fawaterk_fee_fixed
            gateway_fees_deduction = pct_fee + fixed_fee

        # 🔥 تأمين محافظ التجار بالـ Row Locking أثناء إضافة الأرباح
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet_obj, _ = Wallet.objects.get_or_create(merchant=merchant)
                # القفل السحري يمنع تداخل العمليات
                wallet = Wallet.objects.select_for_update().get(id=wallet_obj.id) 
                
                prod_rev = data['product_revenue']
                comp = data['compensation']
                
                shipping_income = Decimal('0.00')
                shipping_desc = ""
                is_shipping_compensated = False

                if instance.merchant == merchant:
                    # خصم رسوم البوابة من إيرادات التاجر الأساسي إذا كان الدفع إلكتروني
                    if is_electronic and gateway_fees_deduction > 0:
                        prod_rev -= gateway_fees_deduction
                        if prod_rev < Decimal('0.00'): 
                            prod_rev = Decimal('0.00') # حماية من الرصيد السالب

                    if instance.shipping_cost > 0:
                        shipping_income = instance.shipping_cost
                        shipping_desc = "شحن مدفوع"
                    else:
                        is_platform_funded = False
                        for item in instance.items.all():
                            try:
                                offer = item.product_size.product.active_offer
                                if offer and offer.is_platform_offer and offer.free_shipping and item.quantity >= offer.free_shipping_threshold:
                                    is_platform_funded = True; break
                            except: pass
                        
                        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=instance.governorate).first()
                        orig_ship = rate_obj.rate if rate_obj else Decimal('50.00')

                        if is_platform_funded:
                            shipping_income, shipping_desc, is_shipping_compensated = orig_ship, "تعويض شحن (عرض منصة)", True
                        elif instance.is_first_order:
                            shipping_income, shipping_desc, is_shipping_compensated = orig_ship, "تعويض شحن (أول طلب)", True
                        elif hasattr(instance, 'admin_discount') and instance.admin_discount > 0:
                            shipping_income, shipping_desc, is_shipping_compensated = orig_ship, "تعويض شحن (قسيمة الإدارة)", True
                        else:
                            shipping_income, shipping_desc = Decimal('0.00'), "شحن مجاني (عرض متجرك)"

                extra_desc = f" | {shipping_desc}" if shipping_desc else ""
                if comp > 0: extra_desc += f" | يشمل تعويضات {comp} ج.م"
                
                # إضافة تنويه برسوم فواتيرك في وصف العملية للتاجر
                if is_electronic and instance.merchant == merchant and gateway_fees_deduction > 0:
                    extra_desc += f" | مخصوم رسوم بوابة {gateway_name} ({round(gateway_fees_deduction, 2)} ج.م)"

                if is_electronic:
                    total_deposit = prod_rev + shipping_income + comp
                    if total_deposit > 0:
                        wallet.pending_balance += total_deposit
                        tx = WalletTransaction(
                            wallet=wallet, amount=total_deposit, transaction_type=WalletTransaction.TxType.PENDING,
                            description=f"مستحقات طلب إلكتروني #{instance.order_id}{extra_desc}",
                            balance_after=wallet.balance, is_released=False
                        )
                        if hasattr(tx, 'related_order_id'): tx.related_order_id = instance.order_id
                        tx.save()
                else:
                    total_comp_only = comp
                    if is_shipping_compensated: total_comp_only += shipping_income
                    if total_comp_only > 0:
                        wallet.pending_balance += total_comp_only
                        tx = WalletTransaction(
                            wallet=wallet, amount=total_comp_only, transaction_type=WalletTransaction.TxType.COMPENSATION,
                            description=f"تعويضات طلب كاش #{instance.order_id}{extra_desc}",
                            balance_after=wallet.balance, is_released=False
                        )
                        if hasattr(tx, 'related_order_id'): tx.related_order_id = instance.order_id
                        tx.save()

                wallet.save()

@receiver(post_save, sender=DepositRequest)
def process_deposit(sender, instance, **kwargs):
    if instance.status == DepositRequest.Status.APPROVED:
        desc = f"شحن رصيد (طلب #{instance.id})"
        if WalletTransaction.objects.filter(description=desc).exists(): return

        with transaction.atomic():
            # 🔥 تأمين محفظة التاجر عند شحن الرصيد الإداري
            wallet = Wallet.objects.select_for_update().get(merchant=instance.merchant)
            wallet.balance += instance.amount 
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet, amount=instance.amount, transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=desc, balance_after=wallet.balance
            )

@receiver(post_save, sender=Order)
def handle_referral_on_cancel_or_return(sender, instance, created, **kwargs):
    """
    معالجة ثغرات نظام الإحالة عند الإلغاء أو الإرجاع
    """
    if created: return

    # 1. إرجاع رصيد الإحالة للعميل إذا ألغى/أرجع طلبه الذي استخدم فيه الرصيد (المخزن في admin_discount)
    if instance.status in [Order.Status.CANCELLED, Order.Status.RETURNED]:
        if instance.admin_discount > 0 and not getattr(instance, '_referral_refunded', False):
            with transaction.atomic():
                from accounts.models import User
                locked_customer = User.objects.select_for_update().get(id=instance.customer.id)
                locked_customer.referral_balance += instance.admin_discount
                locked_customer.save()
            
            # نضع flag في الذاكرة لمنع الاسترداد المتكرر بالخطأ
            instance._referral_refunded = True
            
            Notification.objects.create(
                recipient=instance.customer, title="استرداد رصيد إحالة 🔄", 
                message=f"تم إرجاع {instance.admin_discount} ج.م لرصيد دعواتك بسبب إرجاع الطلب #{instance.order_id}."
            )

    # 2. سحب المكافأة من "الداعي" إذا قام "المدعو" بعمل مرتجع للطلب (لمنع التحايل)
    if instance.status == Order.Status.RETURNED:
        inviter = instance.customer.invited_by
        if inviter:
            # التحقق: هل أخذ المكافأة فعلاً على هذا الطلب مسبقاً؟
            rewarded_notification = Notification.objects.filter(
                recipient=inviter, message__contains=f"الطلب #{instance.order_id}"
            ).first()
            
            if rewarded_notification:
                settings_obj = SiteSetting.get_settings(instance.country)
                reward = settings_obj.referral_reward_amount if settings_obj else Decimal('50.00')
                
                with transaction.atomic():
                    from accounts.models import User
                    locked_inviter = User.objects.select_for_update().get(id=inviter.id)
                    locked_inviter.referral_balance -= reward
                    # حماية حتى لا يصبح الرصيد بالسالب
                    if locked_inviter.referral_balance < 0: 
                        locked_inviter.referral_balance = Decimal('0.00')
                    locked_inviter.save()
                    
                Notification.objects.create(
                    recipient=inviter, title="سحب مكافأة إحالة ⚠️", 
                    message=f"تم خصم {reward} ج.م من رصيدك لأن صديقك قام بعمل مرتجع للطلب #{instance.order_id}."
                )
                rewarded_notification.delete() # نحذف إشعار المكافأة القديم