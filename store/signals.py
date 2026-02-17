from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from .models import Order, OrderItem, ProductSize, Wallet, WalletTransaction, DepositRequest

# 1. تحديث إجمالي الطلب (للعرض فقط)
@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def update_order_totals(sender, instance, **kwargs):
    order = instance.order
    # (نحسب المجموع فقط للعرض، ولا نضيف رسوم هنا لأنها تضاف في Checkout)
    current_items = order.items.all()
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
    # الأموال تضاف فقط عند التسليم (DELIVERED)
    if instance.status == Order.Status.DELIVERED:
        
        # 1. منع التكرار: هل تم دفع عمولة لهذا الطلب من قبل؟
        if WalletTransaction.objects.filter(related_order_id=instance.order_id).exists():
            print(f"تم حساب أرباح الطلب {instance.order_id} مسبقاً. تجاهل.")
            return

        merchant_earnings = {}

        for item in instance.items.all():
            merchant = item.product_size.product.merchant
            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = Decimal('0.00')
            
            # أ. الحسابات
            # السعر الذي دفعه العميل
            price_paid = item.price_at_purchase
            # السعر الأصلي (لحساب التعويض)
            base_price = item.product_size.product.base_price
            # الكمية
            qty = Decimal(item.quantity)
            
            # ب. حساب التعويض (إذا كان عرض منصة)
            compensation = Decimal('0.00')
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_platform_offer and offer.is_active:
                    compensation = base_price - price_paid
            except:
                pass

            # ج. خصم عمولة المنصة (المحددة عند قبول المنتج)
            # نأخذ العمولة من المنتج نفسه
            commission = item.product_size.product.admin_commission * qty

            # د. المعادلة النهائية للربح
            # (السعر المدفوع + التعويض) - عمولة المنصة
            # لاحظ: الشحن لا يدخل هنا (الشحن يذهب لشركة الشحن عادة، أو يضاف بحسبة منفصلة لو التاجر هو اللي بيشحن)
            # لو التاجر هو اللي بيشحن، مفروض نضيف shipping_cost هنا. سنفترض ذلك.
            
            net_profit = ((price_paid + compensation) * qty) - commission
            
            merchant_earnings[merchant] += net_profit

        # 2. التنفيذ
        with transaction.atomic():
            for merchant, amount in merchant_earnings.items():
                # إضافة الشحن للتاجر (لأنه هو من قام بالتوصيل في نموذج Marketplace)
                shipping_income = instance.shipping_cost if instance.merchant == merchant else 0
                
                total_to_deposit = amount + shipping_income
                
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                # إضافة للرصيد المعلق فقط (Pending Balance)
                wallet.pending_balance += total_to_deposit
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=total_to_deposit,
                    transaction_type=WalletTransaction.TxType.PENDING, # معلق
                    related_order_id=instance.order_id,
                    description=f"أرباح طلب #{instance.order_id} (معلقة)",
                    balance_after=wallet.balance # الرصيد المتاح لم يتغير
                )

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