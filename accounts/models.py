from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    # تعريف أنواع المستخدمين
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "عميل"
        MERCHANT = "MERCHANT", "تاجر"
        OWNER = "OWNER", "Owner (مالك)"
        ADMIN_LVL2 = "ADMIN_LVL2", "مشرف درجة ثانية"
        ADMIN_LVL3 = "ADMIN_LVL3", "مشرف درجة ثالثة (خدمة عملاء)"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    
    # البيانات الأساسية للكل
    phone_primary = models.CharField(max_length=15, unique=True, verbose_name="رقم الهاتف الأساسي")
    phone_secondary = models.CharField(max_length=15, blank=True, null=True, verbose_name="رقم هاتف احتياطي")
    
    # بيانات الأمان
    device_id = models.CharField(max_length=255, blank=True, null=True, help_text="لمنع تكرار الحسابات من نفس الجهاز")
    is_banned = models.BooleanField(default=False, verbose_name="محظور")

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"

# نموذج العنوان للعملاء (يمكن إضافته لاحقاً، لكن نضعه للتأسيس)
class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    governorate = models.CharField(max_length=50, verbose_name="المحافظة")
    city = models.CharField(max_length=50, verbose_name="المدينة")
    details = models.TextField(verbose_name="تفاصيل العنوان")
    
    def __str__(self):
        return f"{self.city} - {self.user.username}"