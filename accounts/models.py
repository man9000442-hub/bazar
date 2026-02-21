from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

# تعريف الدور المخصص (إذا كنت تستخدمه في النظام الإداري الجديد)
class CustomRole(models.Model):
    name = models.CharField(max_length=50, unique=True)
    permissions = models.TextField(default="")
    def __str__(self): return self.name

class User(AbstractUser):
    # تعريف أنواع المستخدمين (Choices)
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "عميل"
        MERCHANT = "MERCHANT", "تاجر"
        OWNER = "OWNER", "Owner (مالك)"
        ADMIN_LVL2 = "ADMIN_LVL2", "مشرف درجة ثانية"
        ADMIN_LVL3 = "ADMIN_LVL3", "مشرف درجة ثالثة"

    # الحقول الأساسية
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone_primary = models.CharField(max_length=15, unique=True, verbose_name="رقم الهاتف")
    phone_secondary = models.CharField(max_length=15, blank=True, null=True)
    device_id = models.CharField(max_length=255, blank=True, null=True)
    is_banned = models.BooleanField(default=False)
    
    # حقل الدور المخصص (للمشرفين)
    custom_role = models.ForeignKey(CustomRole, on_delete=models.SET_NULL, null=True, blank=True)

    # --- نظام الدعوات (Referral System) ---
    # نضعها هنا (خارج كلاس Role)
    referral_code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    invited_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='invitees')
    referral_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name="رصيد الدعوات")
    
    # ملاحظة: نستخدم date_joined الموجود أصلاً في AbstractUser بدلاً من إنشاء join_date

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)

    # دالة التحقق من الصلاحيات
    def has_perm_access(self, perm_name):
        if self.is_superuser or self.role == 'OWNER':
            return True
        if self.custom_role:
            return perm_name in self.custom_role.permissions
        return False

# نموذج العنوان للعملاء (يمكن إضافته لاحقاً، لكن نضعه للتأسيس)
class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    governorate = models.CharField(max_length=50, verbose_name="المحافظة")
    city = models.CharField(max_length=50, verbose_name="المدينة")
    details = models.TextField(verbose_name="تفاصيل العنوان")
    
    def __str__(self):
        return f"{self.city} - {self.user.username}"
    




# تعديل المستخدم ليرتبط بالدور الجديد
