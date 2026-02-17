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
            if not merchant: continue # أمان

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = Decimal('0.00')
            
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
            # العمولة * الكمية
            commission = (item.product_size.product.admin_commission * qty)

            # د. الربح الصافي من المنتج
            # (السعر المدفوع * الكمية) + التعويض - العمولة
            net_item_profit = (price_paid * qty) + compensation - commission
            
            merchant_earnings[merchant] += net_item_profit

        # 2. التنفيذ وإضافة الشحن
        with transaction.atomic():
            for merchant, amount in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                # هـ. حساب الشحن
                shipping_income = Decimal('0.00')
                
                # نتأكد أن هذا التاجر هو صاحب الطلب (لأنه هو من شحن)
                if instance.merchant == merchant:
                    if instance.shipping_cost > 0:
                        # العميل دفع الشحن، التاجر يأخذه
                        shipping_income = instance.shipping_cost
                    
                    elif instance.is_first_order:
                        # شحن مجاني (أول طلب) -> المنصة تعوض التاجر
                        # نحسب السعر الأصلي للشحن لهذه المحافظة
                        rate_obj = MerchantShippingRate.objects.filter(
                            merchant=merchant, governorate=instance.governorate
                        ).first()
                        
                        original_shipping = rate_obj.rate if rate_obj else Decimal('50.00')
                        shipping_income = original_shipping
                        
                        # تسجيل حركة تعويض منفصلة للتوضيح
                        WalletTransaction.objects.create(
                            wallet=wallet,
                            amount=original_shipping,
                            transaction_type=WalletTransaction.TxType.COMPENSATION,
                            related_order_id=instance.order_id,
                            description=f"تعويض شحن مجاني (طلب #{instance.order_id})",
                            balance_after=wallet.balance # لا يؤثر في المتاح الآن
                        )

                # الإجمالي النهائي للتاجر (منتجات + شحن)
                total_to_deposit = amount + shipping_income
                
                # و. الإضافة للرصيد المعلق (Pending)
                wallet.pending_balance += total_to_deposit
                wallet.save()
                
                # ز. تسجيل الحركة الرئيسية
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=total_to_deposit,
                    transaction_type='PENDING', # تأكد أنك أضفت هذا النوع في الموديل
                    related_order_id=instance.order_id,
                    description=f"أرباح معلقة (طلب #{instance.order_id})",
                    balance_after=wallet.balance,
                    is_released=False
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