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
                    'revenue': Decimal('0.00'), 
                    'compensation': Decimal('0.00'),
                    'commission': Decimal('0.00')
                }
            
            # أ. الحسابات
            price_paid = item.price_at_purchase
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
            item_commission = (item.product_size.product.admin_commission * qty)

            # د. تجميع الأرقام
            merchant_earnings[merchant]['revenue'] += (price_paid * qty)
            merchant_earnings[merchant]['compensation'] += compensation
            merchant_earnings[merchant]['commission'] += item_commission

        # 2. التنفيذ
        with transaction.atomic():
            for merchant, data in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                # ما الذي سيضاف للمحفظة؟
                amount_to_add = Decimal('0.00')
                
                # 1. إذا كان الدفع أونلاين: التاجر لم يستلم شيئاً بيده
                # نضيف له (سعر المنتج + التعويضات + الشحن)
                if instance.payment_method == Order.PaymentMethod.ONLINE:
                    amount_to_add += data['revenue'] + data['compensation']
                    if instance.merchant == merchant:
                        amount_to_add += instance.shipping_cost

                # 2. إذا كان الدفع كاش: التاجر استلم (سعر المنتج + الشحن) بيده
                # نضيف له (التعويضات فقط) + (تعويض الشحن المجاني إن وجد)
                else:
                    amount_to_add += data['compensation']
                    # هل كان الشحن مجاني؟ نعوضه
                    if instance.is_first_order and instance.merchant == merchant:
                         # (حساب تعويض الشحن كما سبق)
                         rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=instance.governorate).first()
                         shipping_comp = rate_obj.rate if rate_obj else Decimal('50.00')
                         amount_to_add += shipping_comp

                # 3. خصم العمولة (دائماً تخصم من المحفظة)
                # العمولة تخصم من الرصيد المتاح (Balance) وتظهر كحركة منفصلة بالسالب
                if data['commission'] > 0:
                    wallet.balance -= data['commission']
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=-data['commission'], 
                        transaction_type=WalletTransaction.TxType.SALE, # نوع "خصم عمولة"
                        description=f"خصم عمولة (طلب #{instance.order_id})",
                        balance_after=wallet.balance, is_released=True
                    )

                # 4. إضافة المستحقات (للرصيد المعلق)
                if amount_to_add > 0:
                    wallet.pending_balance += amount_to_add
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=amount_to_add,
                        transaction_type=WalletTransaction.TxType.PENDING,
                        related_order_id=instance.order_id,
                        description=f"مستحقات طلب #{instance.order_id} ({instance.get_payment_method_display()})",
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