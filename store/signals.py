from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from .models import Order, OrderItem, ProductSize, Wallet, WalletTransaction

# 1. تحديث إجمالي الطلب عند تغيير المنتجات
@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def update_order_totals(sender, instance, **kwargs):
    order = instance.order
    
    # لا داعي للحسابات المعقدة إذا كانت مجرد سلة تسوق
    # لكن سنحسبها لتظهر للعميل بشكل صحيح
    
    current_items = order.items.all()
    total_products = sum(item.quantity * item.price_at_purchase for item in current_items)
    
    fixed_fee = Decimal('3.00')
    percentage_fee = Decimal('0.0275')
    
    if total_products > 0:
        platform_fees = fixed_fee + (total_products * percentage_fee)
    else:
        platform_fees = Decimal('0.00')

    order.total_products_price = total_products
    order.platform_fees = round(platform_fees, 2)
    order.final_total = total_products + order.platform_fees + order.shipping_cost
    
    # نستخدم update_fields لتجنب الدخول في حلقة لانهائية (Recursion)
    order.save(update_fields=['total_products_price', 'platform_fees', 'final_total'])


# 2. إدارة المخزون (فقط عند الموافقة)
@receiver(post_save, sender=Order)
def manage_inventory(sender, instance, created, **kwargs):
    if created:
        return

    # إذا وافق المشرف (APPROVED) -> نخصم الكمية
    if instance.status == Order.Status.APPROVED:
        with transaction.atomic():
            for item in instance.items.all():
                ProductSize.objects.filter(pk=item.product_size.pk).update(
                    stock_quantity=F('stock_quantity') - item.quantity
                )

    # إذا تم الإلغاء أو الإرجاع -> نعيد الكمية
    elif instance.status in [Order.Status.CANCELLED, Order.Status.RETURNED]:
        with transaction.atomic():
            for item in instance.items.all():
                ProductSize.objects.filter(pk=item.product_size.pk).update(
                    stock_quantity=F('stock_quantity') + item.quantity
                )


# 3. توزيع الأرباح (فقط عند التسليم)
@receiver(post_save, sender=Order)
def distribute_profits(sender, instance, created, **kwargs):
    if instance.status == Order.Status.DELIVERED:
        
        if WalletTransaction.objects.filter(related_order_id=instance.order_id).exists():
            return

        merchant_earnings = {}

        for item in instance.items.all():
            merchant = item.merchant
            if not merchant:
                merchant = item.product_size.product.merchant

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = Decimal('0.00')
            
            price = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            comm = item.commission if item.commission else Decimal('0.00')
            qty = Decimal(item.quantity)
            
            net_profit = (price - comm) * qty
            merchant_earnings[merchant] += net_profit

        with transaction.atomic():
            for merchant, amount in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=amount,
                    transaction_type=WalletTransaction.TxType.SALE,
                    related_order_id=instance.order_id,
                    description=f"أرباح طلب {instance.order_id}",
                    balance_after=wallet.balance + amount
                )
                
                wallet.balance += amount
                wallet.save()