from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


from django.contrib import admin
from .models import UserFCMToken

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'title', 'details')
    readonly_fields = ('user', 'title', 'status', 'details', 'created_at') # عشان محدش يعدل فيها
@admin.register(UserFCMToken)
class UserFCMTokenAdmin(admin.ModelAdmin):
    # الأعمدة اللي هتظهر في الجدول من بره
    list_display = ('user', 'token_preview', 'created_at') 
    
    # حقول البحث (عشان لو عايز تدور على توكين لعميل معين باسمه أو موبايله)
    search_fields = ('user__username', 'user__first_name', 'user__phone_primary', 'token')
    
    # فلاتر جانبية
    list_filter = ('created_at',)
    
    # عشان التوكين بيبقى طويل جداً، بنعمل دالة تعرض أول 30 حرف بس في الجدول من بره لشياكة المنظر
    def token_preview(self, obj):
        if obj.token and len(obj.token) > 30:
            return f"{obj.token[:30]}..."
        return obj.token
    token_preview.short_description = 'FCM Token'
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