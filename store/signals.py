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
                    'revenue': Decimal('0.00'), # الدخل (سعر + تعويض)
                    'commission': Decimal('0.00') # العمولة المستحقة
                }
            
            # أ. الأسعار
            price_paid = item.price_at_purchase
            base_price = item.product_size.product.base_price
            qty = Decimal(item.quantity)
            
            # ب. التعويض
            compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_platform_offer and offer.is_active and price_paid < base_price:
                    compensation = (base_price - price_paid) * qty
            except: pass

            # ج. العمولة
            item_commission = (item.product_size.product.admin_commission * qty)

            # د. التجميع (نفصل الدخل عن العمولة)
            total_item_revenue = (price_paid * qty) + compensation
            
            merchant_earnings[merchant]['revenue'] += total_item_revenue
            merchant_earnings[merchant]['commission'] += item_commission

        # 2. التنفيذ (حركتين منفصلتين)
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                revenue = data['revenue']
                commission = data['commission']
                
                # أ. إضافة الدخل (شامل الشحن لو وجد)
                shipping_income = instance.shipping_cost if instance.merchant == merchant else 0
                if instance.is_first_order and instance.merchant == merchant:
                     # (منطق تعويض الشحن السابق...)
                     # للتبسيط هنا سنضيفه للدخل
                     pass 

                total_income = revenue + shipping_income
                
                # 1. إضافة الدخل للرصيد المعلق
                wallet.pending_balance += total_income
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=total_income,
                    transaction_type='PENDING',
                    related_order_id=instance.order_id,
                    description=f"إيراد طلب #{instance.order_id}",
                    balance_after=wallet.balance, # المتاح لم يتغير
                    is_released=False
                )

                # 2. خصم العمولة من الرصيد المتاح (فوراً)
                if commission > 0:
                    wallet.balance -= commission # يخصم من المتاح (وقد يصبح سالب)
                    
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        amount=-commission, # بالسالب
                        transaction_type=WalletTransaction.TxType.sale, # أو نوع جديد COMMISSIONS
                        related_order_id=instance.order_id,
                        description=f"خصم عمولة منصة (طلب #{instance.order_id})",
                        balance_after=wallet.balance,
                        is_released=True # هذه عملية نهائية
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