from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.db.models import Avg
from django.urls import reverse
from django.utils import timezone
import uuid


# 1. بروفايل التاجر (بيانات التوثيق KYC)
class MerchantProfile(models.Model):
    class RankChoices(models.TextChoices):
        NONE = 'NONE', 'غير موثق'
        SILVER = 'SILVER', 'توثيق فضي'
        BLUE = 'BLUE', 'توثيق أزرق'
        GOLD = 'GOLD', 'توثيق ذهبي'
        
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='merchant_profile')
    national_id = models.CharField(max_length=14, unique=True, verbose_name="الرقم القومي")
    id_card_front = models.ImageField(upload_to='merchant_ids/', verbose_name="صورة البطاقة (أمام)")
    id_card_back = models.ImageField(upload_to='merchant_ids/', verbose_name="صورة البطاقة (خلف)")
    shop_image = models.ImageField(upload_to='shops/', verbose_name="صورة المحل/الشخصية")
    minimum_balance_required = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="الحد الأدنى للرصيد")
    is_approved = models.BooleanField(default=False, verbose_name="تمت الموافقة من المشرف")
    created_at = models.DateTimeField(auto_now_add=True)
    tax_register_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="رقم السجل الضريبي")                                           
    is_verified = models.BooleanField(default=False, verbose_name="موثق (علامة زرقاء)")
    verification_rank = models.CharField(max_length=10, choices=RankChoices.choices, default=RankChoices.NONE, verbose_name="رتبة التوثيق")
    goods_quantity = models.CharField(max_length=100, verbose_name="كمية البضاعة المحتملة")
    goods_types = models.TextField(verbose_name="أنواع البضاعة")
    goods_average_price = models.CharField(max_length=100, verbose_name="متوسط الأسعار")
    goods_sizes = models.TextField(verbose_name="المقاسات المتاحة")
    free_shipping_threshold = models.PositiveIntegerField(default=0, verbose_name="حد الشحن المجاني (عدد قطع)")
    is_free_shipping_active = models.BooleanField(default=False, verbose_name="تفعيل عرض الشحن المجاني")
    product_limit = models.PositiveIntegerField(default=50, verbose_name="الحد الأقصى للمنتجات")
    subscription_end_date = models.DateField(null=True, blank=True, verbose_name="تاريخ انتهاء عرض المنتجات")          
    
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
    # 🔥 ربط المنتج بالدولة لسهولة الفلترة
    country = models.ForeignKey('accounts.Country', on_delete=models.CASCADE, related_name='products', verbose_name="الدولة", null=True, blank=True)
    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name="القسم")
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200, verbose_name="اسم المنتج")
    description = models.TextField(verbose_name="وصف المنتج")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر الأساسي")
    image = models.ImageField(upload_to='products/', verbose_name="صورة المنتج الرئيسية")
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="مصاريف الشحن")
    is_active = models.BooleanField(default=False, verbose_name="مفعل (موافقة المشرف)")
    is_approved = models.BooleanField(default=False, verbose_name="تمت المراجعة والقبول")
    created_at = models.DateTimeField(auto_now_add=True)
    commission_pct = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, verbose_name="نسبة عمولة المنصة (%)")
    
    def save(self, *args, **kwargs):
        # سحب الدولة أوتوماتيك من التاجر
        if not self.country and self.merchant and self.merchant.user.country:
            self.country = self.merchant.user.country
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
    @property
    def average_rating(self):
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0
        
    @property
    def reviews_count(self):
        return self.reviews.count()
        
    @property
    def has_variations(self):
        return self.variations.exists()

    @property
    def available_colors(self):
        return self.variations.values_list('color_label', flat=True).distinct()

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_gallery/', verbose_name="صورة إضافية")
    
    def __str__(self):
        return f"Image for {self.product.name}"
    
class ProductSize(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations') 
    size_label = models.CharField(max_length=10, verbose_name="المقاس") 
    color_label = models.CharField(max_length=30, verbose_name="اللون", default="Standard") 
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="الكمية المتاحة")
    
    def __str__(self):
        return f"{self.product.name} - {self.color_label} - {self.size_label} ({self.stock_quantity})"

class Wallet(models.Model):
    merchant = models.OneToOneField(MerchantProfile, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="الرصيد الحالي")
    updated_at = models.DateTimeField(auto_now=True)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="رصيد معلق")
    def __str__(self):
        return f"محفظة: {self.merchant.user.username} - {self.balance}"

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
    related_order_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="رقم الطلب المرتبط")
    description = models.CharField(max_length=255, verbose_name="وصف العملية")
    created_at = models.DateTimeField(auto_now_add=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="الرصيد بعد العملية")
    is_released = models.BooleanField(default=False, verbose_name="تم تحرير الرصيد") 
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount}"
    
# 1. جدول المحافظات 
class Governorate(models.Model):
    # 🔥 ربط المحافظة بالدولة
    country = models.ForeignKey('accounts.Country', on_delete=models.CASCADE, related_name='governorates', verbose_name="الدولة", null=True)
    name = models.CharField(max_length=50, verbose_name="اسم المحافظة")

    class Meta:
        unique_together = ('country', 'name') # منع تكرار اسم المحافظة في نفس الدولة

    def __str__(self):
        return f"{self.name} ({self.country.name if self.country else ''})"

class MerchantShippingRate(models.Model):
    merchant = models.ForeignKey('MerchantProfile', on_delete=models.CASCADE, related_name='shipping_rates')
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE)
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name="سعر الشحن")

    class Meta:
        unique_together = ('merchant', 'governorate') 

class Order(models.Model):
    class Status(models.TextChoices):
        CART = "CART",
        WAITING_PAYMENT = "WAITING_PAYMENT", "بانتظار الدفع" 
        PENDING = "PENDING", "قيد الانتظار"
        PREPARING = "PREPARING", "جاري التحضير"
        APPROVED = "APPROVED", "تم التأكيد"
        SHIPPED = "SHIPPED", "تم الشحن"
        DELIVERED = "DELIVERED", "تم التسليم"
        RETURNED = "RETURNED", "مرتجع"
        CANCELLED = "CANCELLED", "ملغي"

    order_id = models.CharField(max_length=20, unique=True, editable=False, verbose_name="رقم الطلب")
    
    # 🔥 ربط الطلب بالدولة
    country = models.ForeignKey('accounts.Country', on_delete=models.PROTECT, related_name='orders', verbose_name="الدولة", null=True, blank=True)
    
    merchant_received_return = models.BooleanField(default=False, verbose_name="تأكيد التاجر لاستلام المرتجع")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders', verbose_name="العميل")
    is_confirmed_by_customer = models.BooleanField(null=True, blank=True, verbose_name="تأكيد العميل")
    rejection_reason = models.TextField(blank=True, null=True, verbose_name="سبب الرفض")
    rating = models.PositiveIntegerField(default=0, verbose_name="التقييم (1-5)")   
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.PROTECT, null=True, blank=True, related_name='merchant_orders')    
    shipping_address = models.TextField(verbose_name="عنوان الشحن")
    shipping_phone = models.CharField(max_length=15, verbose_name="رقم التواصل")
    admin_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="خصم معوض من الإدارة")    
    total_products_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="إجمالي المنتجات")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تكلفة الشحن")
    platform_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="رسوم المنصة") 
    final_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="الإجمالي النهائي")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="حالة الطلب")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الطلب")
    governorate = models.ForeignKey(Governorate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المحافظة")
    is_first_order = models.BooleanField(default=False, verbose_name="أول طلب (شحن مجاني)")
    recipient_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="اسم المستلم")
    
    class PaymentMethod(models.TextChoices):
        COD = "COD", "الدفع عند الاستلام"
        ONLINE = "ONLINE", "دفع إلكتروني (Paymob)"
        WALLET = "WALLET", "محفظة إلكترونية"
        
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.COD, verbose_name="طريقة الدفع")
    paymob_order_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم طلب Paymob المبدئي")    
    paymob_transaction_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم معاملة Paymob")
    
    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = "OR-" + str(uuid.uuid4()).split('-')[0].upper()
        # سحب الدولة أوتوماتيك من العميل
        if not self.country and self.customer and self.customer.country:
            self.country = self.customer.country
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_id} - {self.customer.username}"
    
    def get_total_referral_discount(self):
        total = sum(item.referral_discount for item in self.items.all())
        return total
        
    @property
    def amount_to_collect(self):
        if self.payment_method == 'ONLINE':
            return 0
        discount = self.get_total_referral_discount()
        return self.final_total - discount

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_size = models.ForeignKey(ProductSize, on_delete=models.PROTECT, verbose_name="المنتج (المقاس)")
    quantity = models.PositiveIntegerField(default=1, verbose_name="الكمية")
    commission = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="عمولة المنصة")    
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="السعر وقت الشراء", blank=True, null=True)
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.PROTECT, verbose_name="التاجر", blank=True, null=True)
    referral_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    def clean(self):
        super().clean()
        if self.product_size:
            if self.quantity > self.product_size.stock_quantity:
                 raise ValidationError(f"عفواً، الكمية المتاحة من {self.product_size} هي {self.product_size.stock_quantity} فقط.")

    def save(self, *args, **kwargs):
        self.clean()
        if not self.price_at_purchase:
            self.price_at_purchase = self.product_size.product.base_price
        if not self.merchant:
            self.merchant = self.product_size.product.merchant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} x {self.product_size.product.name}"
        
    @property
    def total_price(self):
        price = self.price_at_purchase if self.price_at_purchase else self.product_size.product.base_price
        return self.quantity * price
    
class PaymobTransaction(models.Model):
    merchant = models.ForeignKey(MerchantProfile, on_delete=models.CASCADE)
    paymob_order_id = models.CharField(max_length=50, unique=True) 
    amount_cents = models.IntegerField() 
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.merchant} - {self.paymob_order_id}"
    
class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product') 

class Offer(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='active_offer')
    discount_percentage = models.PositiveIntegerField(default=0, verbose_name="نسبة الخصم %")
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    is_platform_offer = models.BooleanField(default=False, verbose_name="عرض من المنصة (يوجد تعويض)")
    created_at = models.DateTimeField(auto_now_add=True)
    free_shipping = models.BooleanField(default=False, verbose_name="شحن مجاني")
    free_shipping_threshold = models.PositiveIntegerField(default=1, verbose_name="عند شراء X قطع")

    def __str__(self):
        type_str = "Platform" if self.is_platform_offer else "Merchant"
        return f"{self.discount_percentage}% off - {self.product.name} ({type_str})"
    
    @property
    def is_currently_active(self):
        return self.is_active and self.end_date >= timezone.now()

    @property
    def discounted_price(self):
        percentage = Decimal(self.discount_percentage)
        factor = Decimal(1) - (percentage / Decimal(100))
        return self.product.base_price * factor


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
    link = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"To {self.recipient}: {self.title}"
    

# ====================================================
# 🔥 التعديل الأهم: إعدادات الموقع أصبحت خاصة بكل دولة
# ====================================================
from django.db import models
from django.utils.translation import gettext_lazy as _

class SiteSetting(models.Model):
    country = models.OneToOneField('accounts.Country', on_delete=models.CASCADE, related_name='site_settings', verbose_name=_("الدولة"), null=True, blank=True)
    site_name = models.CharField(max_length=100, default="Elbazaar", verbose_name=_("اسم الموقع/الفرع"))
    platform_fee_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=3.00, verbose_name=_("رسوم ثابتة"))
    platform_fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=2.75, verbose_name=_("نسبة العمولة (%)"))
    min_withdrawal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name=_("الحد الأدنى للسحب"))
    min_wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=200.00, verbose_name=_("المبلغ المحجوز في المحفظة"))
    min_active_balance = models.DecimalField(max_digits=10, decimal_places=2, default=-500.00, verbose_name=_("الحد الأدنى لتفعيل المنتجات"))    
    pending_balance_release_hours = models.PositiveIntegerField(default=24, verbose_name=_("مدة تعليق الرصيد (ساعة)"))
    
    # إعدادات الدعوات
    referral_reward_limit_orders = models.IntegerField(default=1, verbose_name=_("عدد الطلبات المؤهلة للمكافأة"))    
    referral_grace_period_hours = models.IntegerField(default=24, verbose_name=_("مهلة إدخال كود الدعوة (ساعة)"))
    referral_reward_amount = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name=_("قيمة المكافأة"))
    referral_discount_limit_pct = models.IntegerField(default=10, verbose_name=_("أقصى نسبة خصم للمنتج (%)"))   
    
    banner_image = models.ImageField(upload_to='banners/', blank=True, null=True, verbose_name=_("صورة البانر"))

    def __str__(self):
        return f"إعدادات: {self.country.name if self.country else 'عام'}"

    @classmethod
    def get_settings(cls, country):
        # 🔥 تعديل جوهري: نستخدم get_or_create مباشرة لضمان وجود كائن دايماً
        obj, created = cls.objects.get_or_create(country=country)
        return obj

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
        unique_together = ('product', 'user')

class Banner(models.Model):
    # 🔥 ربط البانر بدولة
    country = models.ForeignKey('accounts.Country', on_delete=models.CASCADE, related_name='banners', verbose_name="الدولة", null=True, blank=True)
    image = models.ImageField(upload_to='banners/', verbose_name="صورة البانر")
    link = models.CharField(max_length=255, blank=True, null=True, verbose_name="رابط التوجيه (اختياري)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ ووقت انتهاء العرض (اختياري)")
    
    def is_active(self):
        if self.expires_at:
            return self.expires_at > timezone.now()
        return True 

    def __str__(self):
        return f"Banner {self.id} - {self.country.name if self.country else 'عام'}"
        
class TermsAndCondition(models.Model):
    class DocType(models.TextChoices):
        TERMS = 'TERMS', 'شروط وأحكام'
        PRIVACY = 'PRIVACY', 'سياسة الخصوصية'
        SHIPPING_RETURN = 'SHIPPING_RETURN', 'سياسة الشحن والمرتجعات'  

    class UserType(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'للعملاء'
        MERCHANT = 'MERCHANT', 'للتجار'

    # 🔥 ربط الشروط بدولة (عشان شروط السعودية غير مصر)
    country = models.ForeignKey('accounts.Country', on_delete=models.CASCADE, related_name='terms', verbose_name="الدولة", null=True, blank=True)
    title = models.CharField(max_length=200, verbose_name="عنوان البند")
    content = models.TextField(verbose_name="نص البند")
    order = models.PositiveIntegerField(default=0, verbose_name="الترتيب")
    is_active = models.BooleanField(default=True)
    document_type = models.CharField(max_length=20, choices=DocType.choices, default=DocType.TERMS, verbose_name="نوع المستند")
    user_type = models.CharField(max_length=20, choices=UserType.choices, default=UserType.CUSTOMER, verbose_name="المستخدم المستهدف")
    
    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.country.name if self.country else 'عام'} | {self.title}"
    
class PersonalVoucher(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vouchers', verbose_name="العميل")
    title = models.CharField(max_length=100, verbose_name="عنوان العرض")
    code = models.CharField(max_length=20, unique=True, verbose_name="كود الخصم")
    discount_percentage = models.PositiveIntegerField(default=0, verbose_name="نسبة الخصم %")
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=50.00, verbose_name="الحد الأقصى للخصم بالطلب (ج.م)")
    remaining_items = models.PositiveIntegerField(default=1, verbose_name="رصيد المنتجات المسموح للخصم")
    free_shipping = models.BooleanField(default=False, verbose_name="شحن مجاني؟")
    is_used = models.BooleanField(default=False, verbose_name="نفد الرصيد؟")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name="تاريخ الانتهاء")

    def __str__(self):
        return f"{self.customer.first_name} - {self.code} ({self.remaining_items} منتج متبقي)"
    
class AboutUs(models.Model):
    country = models.ForeignKey('accounts.Country', on_delete=models.CASCADE, related_name='about_us', verbose_name="الدولة", null=True, blank=True)
    content = models.TextField(verbose_name="محتوى صفحة من نحن", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"من نحن - {self.country.name if self.country else 'عام'}"
    
class ReturnRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "قيد المراجعة"
        APPROVED = "APPROVED", "مقبول - بانتظار استلام المرتجع"
        REFUNDED = "REFUNDED", "تم الاستلام وإرجاع الأموال"
        REJECTED = "REJECTED", "مرفوض"

    order = models.OneToOneField('Order', on_delete=models.CASCADE, related_name='return_request', verbose_name="الطلب")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="العميل")
    reason = models.TextField(verbose_name="سبب الإرجاع")
    customer_wallet_number = models.CharField(max_length=20, blank=True, null=True, verbose_name="رقم محفظة العميل (للاسترداد)")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="المبلغ المستحق للعميل")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"مرتجع لطلب #{self.order.id} - {self.get_status_display()}"
        
    def save(self, *args, **kwargs):
        if not self.refund_amount and self.order:
            self.refund_amount = self.order.total_products_price
        super().save(*args, **kwargs)

class DeliveryComplaint(models.Model):
    order = models.OneToOneField('Order', on_delete=models.CASCADE, related_name='complaint', verbose_name="الطلب")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="العميل")
    complaint_text = models.TextField(verbose_name="نص الشكوى")
    is_resolved = models.BooleanField(default=False, verbose_name="تم الحل؟")
    admin_notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات الإدارة (للتسوية)")
    whatsapp_number = models.CharField(max_length=15, null=True, blank=True, verbose_name="رقم الواتساب للتواصل")    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"شكوى استلام للطلب #{self.order.id}"

class PromoPopup(models.Model):
    # 🔥 ربط الإعلان بدولة معينة (عشان متطلعش إعلانات بالغلط لدولة تانية)
    country = models.ForeignKey('accounts.Country', on_delete=models.CASCADE, related_name='popups', verbose_name="الدولة", null=True, blank=True)
    title = models.CharField(max_length=200, verbose_name="عنوان الإعلان")
    image = models.ImageField(upload_to='promo_popups/', verbose_name="صورة الإعلان")
    custom_link = models.URLField(blank=True, null=True, verbose_name="رابط مخصص خارجي")
    offer = models.ForeignKey('Offer', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="اربط بعرض نشط")
    start_time = models.DateTimeField(verbose_name="تاريخ ووقت بداية الظهور")
    end_time = models.DateTimeField(verbose_name="تاريخ ووقت الانتهاء والامخفاء")
    is_active = models.BooleanField(default=False, verbose_name="مفعل")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_link(self):
        if self.offer and self.offer.product:
            return reverse('product_detail', args=[self.offer.product.id])
        return self.custom_link or "#"

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("عفواً! وقت الانتهاء يجب أن يكون بعد وقت البداية.")
                
        if self.is_active and self.start_time and self.end_time:
            overlapping = PromoPopup.objects.filter(
                is_active=True,
                country=self.country, # مقارنة مع نفس الدولة فقط
                end_time__gt=self.start_time,
                start_time__lt=self.end_time
            ).exclude(pk=self.pk)
            
            if overlapping.exists():
                raise ValidationError("يوجد إعلان آخر مفعل يتعارض مع هذا التوقيت في هذه الدولة! يرجى اختيار توقيت مختلف.")

    class Meta:
        verbose_name = "إعلان منبثق (Popup)"