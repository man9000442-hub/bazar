from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')), 
    path('user/', include('accounts.urls')), # مساراتنا الخاصة (مثل إكمال البروفايل)
    path('', include('store.urls')),
    path('merchant/', include('merchant_panel.urls')),
    path('super/', include('supervisor.urls')), 
]

# لكي تظهر الصور أثناء التطوير
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)