from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.db.models import Avg


# 1. بروفايل التاجر (بيانات التوثيق KYC)
class MerchantProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='merchant_profile')
    national_id = models.CharField(max_length=14, unique=True, verbose_name="الرقم القومي")
    id_card_front = models.ImageField(upload_to='merchant_ids/', verbose_name="صورة البطاقة (أمام)")
    id_card_back = models.ImageField(upload_to='merchant_ids/', verbose_name="صورة البطاقة (خلف)")
    shop_image = models.ImageField(upload_to='shops/', verbose_name="صورة المحل/الشخصية")
    minimum_balance_required = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, 
        verbose_name="الحد الأدنى للرصيد"
    )
    is_approved = models.BooleanField(default=False, verbose_name="تمت الموافقة من المشرف")
    created_at = models.DateTimeField(auto_now_add=True)
    tax_register_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="رقم السجل الضريبي")                                           

    goods_quantity = models.CharField(max_length=100, verbose_name="كمية البضاعة المحتملة")
    goods_types = models.TextField(verbose_name="أنواع البضاعة")
    goods_average_price = models.CharField(max_length=100, verbose_name="متوسط الأسعار")
    goods_sizes = models.TextField(verbose_name="المقاسات المتاحة")
    free_shipping_threshold = models.PositiveIntegerField(default=0, verbose_name="حد الشحن المجاني (عدد قطع)")
    is_free_shipping_active = models.BooleanField(default=False, verbose_name="تفعيل عرض الشحن المجاني")      
    def __str__(self):
        return f"متجر: {self.user.username}"
    

class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم القسم")
    image = models.ImageField(upload_to='categories/', verbose_name="صورة القسم", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"

# 2. المنتج (البيانات العامة)
class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name="القسم")
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200, verbose_name="اسم المنتج")
    description = models.TextField(verbose_name="وصف المنتج")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر الأساسي")
    image = models.ImageField(upload_to='products/', verbose_name="صورة المنتج الرئيسية")
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="مصاريف الشحن")
    is_active = models.BooleanField(default=False, verbose_name="مفعل (موافقة المشرف)")
    created_at = models.DateTimeField(auto_now_add=True)
    commission_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00, 
        verbose_name="نسبة عمولة المنصة (%)"
    )
    def __str__(self):
        return self.name
    
    @property
    def average_rating(self):
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0
        
    @property
    def reviews_count(self):
        return self.reviews.count()

# موديل الصور الإضافية
class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_gallery/', verbose_name="صورة إضافية")
    
    def __str__(self):
        return f"Image for {self.product.name}"
    
# 3. مقاسات المنتج والمخزون (كل مقاس له مخزون منفصل)
class ProductSize(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations') # غيرنا الاسم لـ variations ليكون أدق
    size_label = models.CharField(max_length=10, verbose_name="المقاس") # S, M, L
    color_label = models.CharField(max_length=30, verbose_name="اللون", default="Standard") # أحمر، أزرق
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="الكمية المتاحة")
    
    def __str__(self):
        return f"{self.product.name} - {self.color_label} - {self.size_label} ({self.stock_quantity})"

# 4. نظام المحفظة (Wallet)
class Wallet(models.Model):
    merchant = models.OneToOneField(MerchantProfile, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="الرصيد الحالي")
    updated_at = models.DateTimeField(auto_now=True)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="رصيد معلق")
    def __str__(self):
        return f"محفظة: {self.merchant.user.username} - {self.balance} ج.م"

# 5. سجل المعاملات المالية (Wallet Transactions)
class WalletTransaction(models.Model):
    class TxType(models.TextChoices):
        SALE = "SALE", "ربح مبيعات"
        PENDING = "PENDING", "ربح معلق"
        COMPENSATION = "COMPENSATION", "تعويض (شحن/خصم)"
        WITHDRAWAL = "WITHDRAWAL", "سحب أرباح"
        REFUND_DEDUCTION = "REFUND", "خصم مرتجع"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    transaction_type = models.CharField(max_length=20, choices=TxType.choices, verbose_name="نوع العملية")
    
    # سنربطها لاحقاً بالـ Order ID كنص فقط لتجنب تعقيد العلاقات الدائرية الآن
    related_order_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="رقم الطلب المرتبط")
    description = models.CharField(max_length=255, verbose_name="وصف العملية")
    
    created_at = models.DateTimeField(auto_now_add=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الرصيد بعد العملية")
    is_released = models.BooleanField(default=False, verbose_name="تم تحرير الرصيد") # <--- أضفه هنا
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount}"
    

import uuid # نحتاج هذه المكتبة لتوليد Order ID

# ... (الكود السابق الخاص بالتاجر والمنتجات والمحفظة موجود بالأعلى) ...
# 1. جدول المحافظات (قائمة ثابتة يضيفها الأدمن)
class Governorate(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="اسم المحافظة")

    def __str__(self):
        return self.name

# 2. جدول أسعار شحن التاجر
class MerchantShippingRate(models.Model):
    merchant = models.ForeignKey('MerchantProfile', on_delete=models.CASCADE, related_name='shipping_rates')
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE)
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name="سعر الشحن")

    class Meta:
        unique_together = ('merchant', 'governorate') # لمنع تكرار السعر لنفس المحافظة
# 6. الطلب (Order)
class Order(models.Model):
    class Status(models.TextChoices):
        CART = "CART",
        WAITING_PAYMENT = "WAITING_PAYMENT", "بانتظار الدفع" # <--- جديد
        PENDING = "PENDING", "قيد الانتظار"
        APPROVED = "APPROVED", "تم التأكيد"
        SHIPPED = "SHIPPED", "تم الشحن"
        DELIVERED = "DELIVERED", "تم التسليم"
        RETURNED = "RETURNED", "مرتجع"
        CANCELLED = "CANCELLED", "ملغي"

    # Order ID فريد (مثل: OR-9A2B3C)
    order_id = models.CharField(max_length=20, unique=True, editable=False, verbose_name="رقم الطلب")
    
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders', verbose_name="العميل")
    is_confirmed_by_customer = models.BooleanField(null=True, blank=True, verbose_name="تأكيد العميل")
    rejection_reason = models.TextField(blank=True, null=True, verbose_name="سبب الرفض")
    rating = models.PositiveIntegerField(default=0, verbose_name="التقييم (1-5)")   
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.PROTECT, null=True, blank=True, related_name='merchant_orders')    # تفاصيل العنوان (يتم حفظها كنص لضمان عدم تغيرها في السجلات التاريخية)
    shipping_address = models.TextField(verbose_name="عنوان الشحن")
    shipping_phone = models.CharField(max_length=15, verbose_name="رقم التواصل")
    
    # الحسابات المالية
    total_products_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="إجمالي المنتجات")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الشحن")
    platform_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="رسوم المنصة") # 3 EGP + 2.75%
    final_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="الإجمالي النهائي")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="حالة الطلب")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    governorate = models.ForeignKey(Governorate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المحافظة")
    # تتبع العروض (اختياري للمستقبل)
    is_first_order = models.BooleanField(default=False, verbose_name="أول طلب (شحن مجاني)")
    class PaymentMethod(models.TextChoices):
        COD = "COD", "الدفع عند الاستلام"
        ONLINE = "ONLINE", "دفع إلكتروني (Paymob)"
    
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.COD, verbose_name="طريقة الدفع")
    def save(self, *args, **kwargs):
        # توليد Order ID تلقائيًا إذا لم يكن موجودًا
        if not self.order_id:
            self.order_id = "OR-" + str(uuid.uuid4()).split('-')[0].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} - {self.customer.username}"


# 7. عناصر الطلب (Order Items)
# ... داخل class OrderItem ...

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_size = models.ForeignKey(ProductSize, on_delete=models.PROTECT, verbose_name="المنتج (المقاس)")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    commission = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="عمولة المنصة")    
    # لاحظ: remove blank=True/null=True here is correct, we handle it in save()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر وقت الشراء", blank=True, null=True)
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.PROTECT, verbose_name="التاجر", blank=True, null=True)

    def clean(self):
        # هذه الدالة تُستدعى قبل الحفظ للتحقق من الصحة
        super().clean()
        if self.product_size:
            # التحقق: هل الكمية المطلوبة أكبر من المتاحة؟
            # ملاحظة: إذا كنا نعدل طلب قديم، يجب ألا نخصم الكمية التي حجزناها سابقاً
            if self.quantity > self.product_size.stock_quantity:
                 raise ValidationError(f"عفواً، الكمية المتاحة من {self.product_size} هي {self.product_size.stock_quantity} فقط.")


    def save(self, *args, **kwargs):
        # 1. جلب السعر تلقائياً من المنتج إذا لم يتم إدخاله
        self.clean()
        if not self.price_at_purchase:
            self.price_at_purchase = self.product_size.product.base_price
        
        # 2. جلب التاجر تلقائياً من المنتج
        if not self.merchant:
            self.merchant = self.product_size.product.merchant

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product_size.product.name}"
        
    @property
    def total_price(self):
        # تأمين في حالة لم يتم الحفظ بعد
        price = self.price_at_purchase if self.price_at_purchase else self.product_size.product.base_price
        return self.quantity * price
    


class PaymobTransaction(models.Model):
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE)
    paymob_order_id = models.CharField(max_length=50, unique=True) # رقم الطلب عند Paymob
    amount_cents = models.IntegerField() # المبلغ بالقروش
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.merchant} - {self.paymob_order_id}"
    

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product') # لمنع تكرار نفس المنتج في المفضلة


# أضف هذا الكلاس (أو عدله إذا كان موجوداً)
class Offer(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='active_offer')
    discount_percentage = models.PositiveIntegerField(verbose_name="نسبة الخصم %")
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # حقول جديدة للتمييز
    is_platform_offer = models.BooleanField(default=False, verbose_name="عرض من المنصة (يوجد تعويض)")
    created_at = models.DateTimeField(auto_now_add=True)
    free_shipping = models.BooleanField(default=False, verbose_name="شحن مجاني")
    free_shipping_threshold = models.PositiveIntegerField(default=1, verbose_name="عند شراء X قطع")

    def __str__(self):
        type_str = "Platform" if self.is_platform_offer else "Merchant"
        return f"{self.discount_percentage}% off - {self.product.name} ({type_str})"
    
    @property
    def discounted_price(self):
        # التحويل لـ Decimal قبل الضرب
        percentage = Decimal(self.discount_percentage)
        factor = Decimal(1) - (percentage / Decimal(100))
        return self.product.base_price * factor


# نموذج طلب شحن الرصيد (يدوي عبر فودافون كاش مثلاً)
class DepositRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "قيد المراجعة"
        APPROVED = "APPROVED", "تمت الموافقة"
        REJECTED = "REJECTED", "مرفوض"

    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name='deposit_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    proof_image = models.ImageField(upload_to='deposits/', verbose_name="صورة التحويل")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.merchant.user.username} - {self.amount}"
    

class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=100)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # رابط اختياري للتوجيه (مثلاً لصفحة الطلب)
    link = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"To {self.recipient}: {self.title}"
    


# إعدادات الموقع العامة (Singleton Model - صف واحد فقط)
class SiteSetting(models.Model):
    site_name = models.CharField(max_length=100, default="Elbazaar", verbose_name="اسم الموقع")
    platform_fee_fixed = models.DecimalField(max_digits=5, decimal_places=2, default=3.00, verbose_name="رسوم ثابتة (ج.م)")
    platform_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=2.75, verbose_name="نسبة العمولة (%)")
    min_withdrawal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name="الحد الأدنى للسحب")
    
    # 2. المبلغ المحجوز في المحفظة (لا يمكن سحبه)
    min_wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=200.00, verbose_name="المبلغ المحجوز في المحفظة")
    
    # 3. الحد الأدنى لتفعيل المنتجات
    min_active_balance = models.DecimalField(max_digits=10, decimal_places=2, default=-500.00, verbose_name="الحد الأدنى لتفعيل المنتجات")    
    # صور البانر (يمكن زيادتها)
    banner_image = models.ImageField(upload_to='banners/', blank=True, null=True, verbose_name="صورة البانر الرئيسي")
    
    def __str__(self):
        return "إعدادات الموقع"

    # دالة للتأكد من وجود صف واحد فقط
    def save(self, *args, **kwargs):
        if not self.pk and SiteSetting.objects.exists():
            return # منع إنشاء أكثر من إعداد
        super().save(*args, **kwargs)
    

class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "قيد المراجعة"
        APPROVED = "APPROVED", "تم التحويل"
        REJECTED = "REJECTED", "مرفوض"

    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    phone_number = models.CharField(max_length=15, verbose_name="رقم المحفظة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"سحب {self.amount} لـ {self.merchant}"

class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user') # تقييم واحد لكل مستخدم للمنتج