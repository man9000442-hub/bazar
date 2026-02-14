from django.urls import path
from . import views

urlpatterns = [
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('merchant-onboarding/', views.merchant_onboarding, name='merchant_onboarding'),
     path('profile/', views.profile_view, name='profile'), # المسار الجديد
]