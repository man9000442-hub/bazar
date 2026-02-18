from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from accounts.views import signup_choice # تأكد أن هذا الـ View موجود

urlpatterns = [
    # لوحة الأدمن
    path('admin/', admin.site.urls),
    
    # حسابات المستخدمين
    path('accounts/signup/', signup_choice, name='account_signup'), # خطف رابط التسجيل
    path('accounts/', include('allauth.urls')),
    path('user/', include('accounts.urls')),
    
    # تطبيقاتنا
    path('merchant/', include('merchant_panel.urls')),
    path('super/', include('supervisor.urls')),
    path('', include('store.urls')),
    
    # --- الروابط السحرية لتشغيل الصور (حتى لو DEBUG=False) ---
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
]