from django.urls import path
from . import views

urlpatterns = [
    path('', views.supervisor_dashboard, name='supervisor_dashboard'),
    
    # المنتجات
    path('products/pending/', views.pending_products, name='super_pending_products'),
    path('products/review/<int:pk>/', views.product_review, name='super_product_review'),
    
    # التجار
    path('merchants/pending/', views.pending_merchants, name='super_pending_merchants'),
    path('merchants/approve/<int:pk>/', views.approve_merchant, name='super_approve_merchant'),
    
    # العروض
    path('offers/create/', views.create_platform_offer, name='super_create_offer'),
    path('orders/all/', views.all_orders, name='super_all_orders'),
    path('deposits/pending/', views.pending_deposits, name='super_pending_deposits'),
    path('deposits/approve/<int:pk>/', views.approve_deposit, name='super_approve_deposit'),
    path('team/', views.team_management, name='super_team'),
]