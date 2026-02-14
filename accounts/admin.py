from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

# تخصيص واجهة المستخدمين في الأدمن
class CustomUserAdmin(UserAdmin):
    # 1. الأعمدة التي تظهر في القائمة الخارجية
    list_display = ('username', 'phone_primary', 'role', 'first_name', 'is_active', 'is_staff')
    
    # 2. فلاتر البحث والفرز (على اليمين)
    list_filter = ('role', 'is_active', 'is_staff', 'date_joined')
    
    # 3. حقول البحث (Search Box)
    search_fields = ('username', 'phone_primary', 'first_name', 'email')
    
    # 4. تقسيم الحقول داخل صفحة التعديل (Fieldsets)
    fieldsets = UserAdmin.fieldsets + (
        ('بيانات إضافية', {'fields': ('role', 'phone_primary', 'phone_secondary', 'device_id', 'is_banned')}),
    )
    
    # 5. الحقول عند إضافة مستخدم جديد
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('بيانات إضافية', {'fields': ('email', 'role', 'phone_primary')}),
    )

# تسجيل الموديل مع التخصيص الجديد
admin.site.register(User, CustomUserAdmin)