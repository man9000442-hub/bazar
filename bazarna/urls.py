from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from accounts.views import signup_choice 
from django.conf.urls.i18n import i18n_patterns
from django.views.generic import TemplateView
from store.views import custom_404_view, custom_500_view

# الروابط التي لا نريد وضع كود لغة قبلها (مثل رابط تغيير اللغة نفسه)
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

# الروابط التي ستظهر مسبوقة بـ /ar/ أو /en/
urlpatterns += i18n_patterns(
    # لوحة الأدمن
    path('admin/', admin.site.urls),
    
    # حسابات المستخدمين
    path('accounts/signup/', signup_choice, name='account_signup'),     
    path('accounts/', include('accounts.urls')),     
    path('accounts/', include('allauth.urls')),
    
    # تطبيقات المشروع
    path('merchant/', include('merchant_panel.urls')),
    path('super/', include('supervisor.urls')),
    path('', include('store.urls')),
    path('support/', include('support.urls')),
    
    # ملف الـ Service Worker للاشعارات
    path('firebase-messaging-sw.js', TemplateView.as_view(
        template_name='firebase-messaging-sw.js', 
        content_type='application/javascript'
    ), name='firebase-messaging-sw'),

    # روابط الميديا والاستاتيك (لبيئة التطوير)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),

    # 🔥 السطر السحري: إظهار /ar/ دائماً حتى لو كانت اللغة الافتراضية
    prefix_default_language=True,
)

handler404 = custom_404_view
handler500 = custom_500_view