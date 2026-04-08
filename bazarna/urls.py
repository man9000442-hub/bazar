from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from accounts.views import signup_choice # تأكد أن هذا الـ View موجود
from django.conf.urls.i18n import i18n_patterns
from django.views.generic import TemplateView
from store.views import custom_404_view, custom_500_view
urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
]

urlpatterns += i18n_patterns(
    # لوحة الأدمن
    path('admin/', admin.site.urls),
    
    path('i18n/', include('django.conf.urls.i18n')),
    # حسابات المستخدمين
    path('accounts/signup/', signup_choice, name='account_signup'), 
    
    # 🌟 عدلنا كلمة user وخليناها accounts، وحطيناها قبل allauth 🌟
    path('accounts/', include('accounts.urls')), 
    
    path('accounts/', include('allauth.urls')),
    
    # تطبيقاتنا
    path('merchant/', include('merchant_panel.urls')),
    path('super/', include('supervisor.urls')),
    path('', include('store.urls')),
    path('support/', include('support.urls')),
    
    path('firebase-messaging-sw.js', TemplateView.as_view(
        template_name='firebase-messaging-sw.js', 
        content_type='application/javascript'
    ), name='firebase-messaging-sw'),

    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
)

handler404 = custom_404_view
handler500 = custom_500_view