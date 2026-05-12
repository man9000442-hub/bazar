from django.views.decorators.csrf import csrf_exempt
from . import views
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

# from .api_views import (
#     # LoginAPIView, 
#     # CustomerRegisterAPIView, 
#     # ProfileAPIView, 
#     # MerchantOnboardingAPIView,
#     # GoogleLoginAPIView # سنؤجله قليلاً حتى نضبط الأساسيات
#     NativeLoginAPI,NativeGoogleLoginAPI
# )

urlpatterns = [
    # التسجيل الجديد (3 صفحات)
    path('signup/', views.signup_choice, name='signup_choice'),
    path('signup/customer/', views.customer_signup, name='customer_signup'),
    path('signup/merchant/', views.merchant_signup, name='merchant_signup'),

    # إكمال البيانات (لجوجل)
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('merchant-onboarding/', views.merchant_onboarding, name='merchant_onboarding'),
    
    # البروفايل
    path('profile/', views.profile_view, name='profile'),
    path('terms/', views.terms_view, name='terms_view'),
    path('merchant/profile/', views.merchant_profile_view, name='merchant_profile'),
    path('merchant/profile/update/', views.merchant_profile_update, name='merchant_profile_update'),
    path('merchant/profile/change-password/', views.merchant_change_password, name='merchant_change_password'),
    path('merchant/notifications/', views.merchant_notifications_view, name='merchant_notifications'),
    path('delete-account/', views.delete_account_request, name='delete-account'),
    path('save-fcm-token/', views.save_fcm_token, name='save_fcm_token'),
    path('settings/', views.user_settings, name='user_settings'),

]

















 # مسارات المصادقة (Authentication)
    # path('api/login/', LoginAPIView.as_view(), name='api_login'),
    # path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # لتجديد التوكن في فلاتر
    # path('api/register/customer/', CustomerRegisterAPIView.as_view(), name='api_register_customer'),
    
    # # مسارات الحساب (Profile & Onboarding)
    # path('api/profile/', ProfileAPIView.as_view(), name='api_profile'),
    # path('api/merchant/onboarding/', MerchantOnboardingAPIView.as_view(), name='api_merchant_onboarding'),
    # path('api/update-fcm-token/', api_views.update_fcm_token_api, name='api_update_fcm_token'),
#]