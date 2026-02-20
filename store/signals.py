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
    if instance.status == Order.Status.DELIVERED:
        
        if WalletTransaction.objects.filter(related_order_id=instance.order_id).exists():
            return

        merchant_earnings = {}

        for item in instance.items.all():
            merchant = item.product_size.product.merchant
            if not merchant: continue

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = {
                    'product_revenue': Decimal('0.00'), # إيراد المنتجات فقط
                    'commission': Decimal('0.00')
                }
            
            # أ. الأسعار
            price_paid = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            
            # ب. التعويض عن العروض
            compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_platform_offer and offer.is_active and price_paid < base_price:
                    compensation = (base_price - price_paid) * qty
            except: pass

            # ج. العمولة
            pct = item.product_size.product.commission_pct / 100
            commission = (price_paid * pct * qty)

            # د. تجميع إيراد المنتجات (السعر + تعويض العرض)
            total_item_revenue = (price_paid * qty) + compensation
            
            merchant_earnings[merchant]['product_revenue'] += total_item_revenue
            merchant_earnings[merchant]['commission'] += commission

        # 2. التنفيذ
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                product_revenue = data['product_revenue']
                commission = data['commission']
                shipping_income = Decimal('0.00')
                shipping_desc = ""

                # هـ. حساب الشحن
                if instance.merchant == merchant:
                    # 1. شحن مدفوع
                    if instance.shipping_cost > 0:
                        shipping_income = instance.shipping_cost
                        shipping_desc = f"شحن مدفوع (طلب #{instance.order_id})"
                    
                    # 2. شحن مجاني (هل يوجد تعويض؟)
                    else:
                        # أ. عرض منصة
                        is_platform_funded = False
                        for item in instance.items.all():
                            try:
                                offer = item.product_size.product.active_offer
                                if offer and offer.is_platform_offer and offer.free_shipping:
                                    if item.quantity >= offer.free_shipping_threshold:
                                        is_platform_funded = True
                                        break
                            except: pass
                        
                        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=instance.governorate).first()
                        original_shipping = rate_obj.rate if rate_obj else Decimal('50.00')

                        if is_platform_funded:
                            shipping_income = original_shipping
                            shipping_desc = f"تعويض شحن منصة (طلب #{instance.order_id})"
                        
                        elif instance.is_first_order:
                            shipping_income = original_shipping
                            shipping_desc = f"تعويض شحن أول طلب (طلب #{instance.order_id})"
                        
                        else:
                            # عرض تاجر (لا دخل)
                            shipping_income = 0

                # و. تسجيل الحركات (منفصلة للوضوح)
                
                # 1. حركة المنتجات
                if product_revenue > 0:
                    wallet.pending_balance += product_revenue
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=product_revenue,
                        transaction_type='PENDING',
                        related_order_id=instance.order_id,
                        description=f"مبيعات منتجات (طلب #{instance.order_id})",
                        balance_after=wallet.balance, is_released=False
                    )

                # 2. حركة الشحن (إن وجدت)
                if shipping_income > 0:
                    wallet.pending_balance += shipping_income
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=shipping_income,
                        transaction_type='PENDING', # أو COMPENSATION إذا أردت تمييزها
                        related_order_id=instance.order_id,
                        description=shipping_desc,
                        balance_after=wallet.balance, is_released=False
                    )

                # 3. خصم العمولة (من المتاح فوراً)
                if commission > 0:
                    wallet.balance -= commission
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=-commission,
                        transaction_type=WalletTransaction.TxType.SALE,
                        related_order_id=instance.order_id,
                        description=f"خصم عمولة المنصة (طلب #{instance.order_id})",
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