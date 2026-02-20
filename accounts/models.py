from django.db import models
from django.contrib.auth.models import AbstractUser
class CustomRole(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="اسم الدور")
    description = models.TextField(blank=True, null=True)
    
    # قائمة الصلاحيات (نخزنها كنص مفصول بفاصلة، أو ManyToMany)
    # للأسهل، سنستخدم JSONField أو TextField بسيط
    permissions = models.TextField(default="", help_text="أسماء الصلاحيات مفصول بفاصلة (مثلاً: orders, products)")

    def __str__(self):
        return self.name
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
    custom_role = models.ForeignKey(CustomRole, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الدور الإداري")
    def has_perm_access(self, perm_name):
        if self.is_superuser or self.role == 'OWNER':
            return True
        if self.custom_role:
            return perm_name in self.custom_role.permissions.split(',')
        return False    
    
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
    




# تعديل المستخدم ليرتبط بالدور الجديد
