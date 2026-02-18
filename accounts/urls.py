from django.urls import path
from . import views

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
]