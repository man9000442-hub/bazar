from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from django.db.models import F
from decimal import Decimal
from .models import Order, OrderItem, ProductSize, Wallet, WalletTransaction
from .models import SiteSetting
# 1. تحديث إجمالي الطلب عند تغيير المنتجات
from .models import SiteSetting

@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def update_order_totals(sender, instance, **kwargs):
    order = instance.order
    
    # 1. حساب مجموع المنتجات
    # نستخدم السعر المسجل وقت الشراء (سواء كان عرضاً أو سعراً أصلياً)
    current_items = order.items.all()
    total_products = sum(item.quantity * item.price_at_purchase for item in current_items)
    
    # 2. حساب رسوم المنصة
    # (حالياً نجعلها 0 لأن الدفع كاش افتراضياً)
    # إذا أردت تفعيلها، يمكنك قراءة القيم من SiteSetting هنا
    platform_fees = Decimal('0.00')

    # 3. حساب الشحن (يعتمد على ما تم حسابه في Checkout)
    # نحتفظ بالقيمة الحالية للشحن ولا نغيرها هنا لتجنب تصفيرها بالخطأ
    shipping_cost = order.shipping_cost

    # 4. تحديث القيم
    order.total_products_price = total_products
    order.platform_fees = platform_fees
    
    # الإجمالي النهائي
    order.final_total = total_products + platform_fees + shipping_cost
    
    # نستخدم update_fields لمنع الدخول في Loop
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
# ==========================================
@receiver(post_save, sender=Order)
def distribute_profits(sender, instance, created, **kwargs):
    # نعمل فقط عند تحول الحالة لـ "تم التسليم"
    if instance.status == Order.Status.DELIVERED:
        
        # حماية من التكرار (هل تم حساب هذا الطلب من قبل؟)
        if WalletTransaction.objects.filter(related_order_id=instance.order_id).exists():
            return

        # تجميع أرباح كل تاجر
        merchant_earnings = {}

        for item in instance.items.all():
            merchant = item.merchant
            # حماية إضافية للتاجر
            if not merchant:
                merchant = item.product_size.product.merchant

            if merchant not in merchant_earnings:
                merchant_earnings[merchant] = Decimal('0.00')
            
            # 1. السعر الأساسي للمنتج (بدون خصم)
            base_price = item.product_size.product.base_price
            
            # 2. السعر الذي دفعه العميل فعلياً
            price_paid = item.price_at_purchase if item.price_at_purchase else Decimal('0.00')
            
            # 3. حساب التعويض (Compensation Logic)
            # هل هناك عرض "منصة" نشط تسبب في انخفاض السعر؟
            compensation = Decimal('0.00')
            comm = item.product_size.product.admin_commission
            # نحاول الوصول للعرض المرتبط بالمنتج
            try:
                offer = item.product_size.product.active_offer
                # الشرط: العرض نشط + العرض من المنصة + السعر المدفوع أقل من الأصلي
                if offer and offer.is_active and offer.is_platform_offer and price_paid < base_price:
                    compensation = base_price - price_paid
            except:
                pass # لا يوجد عرض أو حدث خطأ
            
            # 4. عمولة المنصة
            comm = item.commission if item.commission else Decimal('0.00')
            
            # 5. المعادلة النهائية لربح التاجر:
            # (السعر المدفوع + التعويض - العمولة) * الكمية
            qty = Decimal(item.quantity)
            net_profit = (price_paid + compensation - comm) * qty
            
            merchant_earnings[merchant] += net_profit

        # تنفيذ التحويلات المالية
        with transaction.atomic():
            for merchant, amount in merchant_earnings.items():
                wallet, _ = Wallet.objects.get_or_create(merchant=merchant)
                
                # تسجيل الحركة في السجل
                WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=amount,
                    transaction_type=WalletTransaction.TxType.SALE,
                    related_order_id=instance.order_id,
                    description=f"أرباح طلب #{instance.order_id}",
                    balance_after=wallet.balance + amount
                )
                
                # تحديث الرصيد الفعلي
                wallet.balance += amount
                wallet.save()


from .models import DepositRequest

@receiver(post_save, sender=DepositRequest)
def process_deposit(sender, instance, **kwargs):
    """
    زيادة رصيد المحفظة تلقائياً عند موافقة الأدمن على طلب الشحن
    """
    if instance.status == DepositRequest.Status.APPROVED:
        # التحقق: هل تمت العملية من قبل؟ (لمنع التكرار)
        desc = f"شحن رصيد (طلب #{instance.id})"
        if WalletTransaction.objects.filter(description=desc).exists():
            return

        with transaction.atomic():
            wallet = instance.merchant.wallet
            amount = instance.amount
            
            # تسجيل الحركة
            WalletTransaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type=WalletTransaction.TxType.COMPENSATION, # نعتبرها تعويض أو إيداع
                description=desc,
                balance_after=wallet.balance + amount
            )
            
            # زيادة الرصيد الفعلي
            wallet.balance += amount
            wallet.save()

from .models import Notification

# 1. إشعار للتاجر عند وصول طلب جديد
@receiver(post_save, sender=Order)
def notify_merchant_new_order(sender, instance, created, **kwargs):
    # نرسل الإشعار فقط عندما يتحول الطلب لـ PENDING (تم التأكيد)
    if instance.status == Order.Status.PENDING:
        # نحتاج لمعرفة كل التجار في هذا الطلب
        merchants = set(item.product_size.product.merchant for item in instance.items.all())
        
        for merchant in merchants:
            Notification.objects.create(
                recipient=merchant.user,
                title="طلب جديد! 📦",
                message=f"لديك طلب جديد #{instance.order_id}. يرجى مراجعته.",
                link=f"/merchant/orders/{instance.order_id}/" # رابط صفحة التفاصيل
            )

# 2. إشعار للعميل عند تغيير الحالة
@receiver(post_save, sender=Order)
def notify_customer_order_status(sender, instance, **kwargs):
    # لا نرسل عند الإنشاء، فقط عند التعديل
    if instance.pk: 
        # (لتبسيط الكود، سنرسل في كل مرة يتم الحفظ بحالة غير CART و PENDING)
        if instance.status in [Order.Status.SHIPPED, Order.Status.DELIVERED]:
            msg = f"تم شحن طلبك #{instance.order_id} 🚚" if instance.status == 'SHIPPED' else f"تم تسليم طلبك #{instance.order_id} ✅"
            
            Notification.objects.create(
                recipient=instance.customer,
                title="تحديث الطلب",
                message=msg,
                link="/my-orders/"
            )