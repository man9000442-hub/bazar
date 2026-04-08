from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import uuid

# ==========================================
# 1. موديل الدولة (الأساس الجديد)
# ==========================================
class Country(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم الدولة")
    code = models.CharField(max_length=10, unique=True, verbose_name="كود الدولة (مثل EG)")
    phone_code = models.CharField(max_length=10, verbose_name="كود الاتصال (مثل +20)")
    currency_name = models.CharField(max_length=50, verbose_name="اسم العملة (مثل جنيه)")
    currency_symbol = models.CharField(max_length=10, verbose_name="رمز العملة (مثل ج.م)")
    is_active = models.BooleanField(default=True, verbose_name="دولة مفعلة")

    # 🔥 إعدادات الدفع لكل دولة منفصلة (عشان كل عملة ليها Integration ID في Paymob)
    paymob_integration_id_card = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID دفع البطاقات")
    paymob_integration_id_wallet = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID دفع المحافظ")

    class Meta:
        verbose_name = "دولة"
        verbose_name_plural = "الدول"

    def __str__(self):
        return f"{self.name} ({self.currency_symbol})"

# ==========================================
# 2. الأدوار المخصصة للمشرفين (مرتبطة بالدولة)
# ==========================================
class CustomRole(models.Model):
    name = models.CharField(max_length=50)
    # ربط الدور بدولة معينة عشان مدير دولة ميشوفش أدوار دولة تانية
    country = models.ForeignKey(Country, on_delete=models.CASCADE, null=True, blank=True, related_name='custom_roles')
    permissions = models.TextField(default="")
    
    def __str__(self):
        return f"{self.name} - {self.country.name if self.country else 'عام'}"

# ==========================================
# 3. موديل المستخدم الأساسي
# ==========================================
class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "عميل"
        MERCHANT = "MERCHANT", "تاجر"
        OWNER = "OWNER", "مالك النظام (سوبر يوزر)"
        COUNTRY_ADMIN = "COUNTRY_ADMIN", "مدير دولة" # 🔥 الرتبة الجديدة
        ADMIN_LVL2 = "ADMIN_LVL2", "مشرف درجة ثانية"
        ADMIN_LVL3 = "ADMIN_LVL3", "مشرف درجة ثالثة"

    # الحقول الأساسية
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    
    # 🔥 ربط المستخدم بدولة (إجباري للمشرفين والتجار، واختياري/إجباري للعميل حسب التسجيل)
    country = models.ForeignKey(Country, on_delete=models.RESTRICT, null=True, blank=True, related_name="users", verbose_name="الدولة التابع لها")

    phone_primary = models.CharField(max_length=20, unique=True, null=True, blank=True)
    phone_secondary = models.CharField(max_length=15, blank=True, null=True)
    device_id = models.CharField(max_length=255, blank=True, null=True)
    is_banned = models.BooleanField(default=False)
    
    # حقل الدور المخصص (للمشرفين)
    custom_role = models.ForeignKey(CustomRole, on_delete=models.SET_NULL, null=True, blank=True)

    # --- نظام الدعوات (Referral System) ---
    referral_code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    invited_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='invitees')
    referral_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="رصيد الدعوات")

    def save(self, *args, **kwargs):
        if self.phone_primary == "":
            self.phone_primary = None
        if not self.referral_code:
            self.referral_code = str(uuid.uuid4())[:8].upper()
            
        # المالك (Owner) ملوش دولة محددة لأنه بيحكم الكل
        if self.role == 'OWNER':
            self.country = None
            self.is_superuser = True
            
        super().save(*args, **kwargs)

    # دالة التحقق من الصلاحيات
    def has_perm_access(self, perm_name):
        if self.is_superuser or self.role == 'OWNER':
            return True # المالك يعمل كل حاجة
            
        if self.role == 'COUNTRY_ADMIN':
            # مدير الدولة معاه كل الصلاحيات بس هنقيده في الـ Views إنه يشوف دولته بس
            return True 
            
        if self.custom_role:
            return perm_name in self.custom_role.permissions
        return False

# ==========================================
# 4. موديل العنوان
# ==========================================
class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    # المحافظة هتبقى مربوطة بالدولة في ملف store/models.py
    governorate = models.CharField(max_length=50, verbose_name="المحافظة")
    city = models.CharField(max_length=50, verbose_name="المدينة")
    details = models.TextField(verbose_name="تفاصيل العنوان")
    
    def __str__(self):
        return f"{self.city} - {self.user.username}"

# ==========================================
# 5. موديلات الإشعارات
# ==========================================
class UserFCMToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fcm_tokens')
    # شلنا الـ unique=True عشان متعملش Crash لو مستخدم دخل بأكتر من حساب من نفس الجهاز
    token = models.CharField(max_length=255, verbose_name="FCM Token")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.token[:20]}..."

class NotificationLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="العميل")
    title = models.CharField(max_length=255, verbose_name="عنوان الإشعار")
    status = models.CharField(max_length=50, verbose_name="الحالة")
    details = models.TextField(blank=True, null=True, verbose_name="تفاصيل/إيرور")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت الإرسال")