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
    path('users/', views.users_list, name='super_users_list'),
path('users/edit/<int:user_id>/', views.user_edit, name='super_user_edit'),
path('users/delete/<int:user_id>/', views.user_delete, name='super_user_delete'),
path('categories/', views.manage_categories, name='super_categories'),
path('categories/delete/<int:pk>/', views.delete_category, name='super_delete_category'),
path('settings/', views.site_settings_view, name='super_site_settings'),
path('withdrawals/pending/', views.pending_withdrawals, name='super_pending_withdrawals'),
path('withdrawals/approve/<int:pk>/', views.approve_withdrawal, name='super_approve_withdrawal'),
path('orders/<str:order_id>/', views.order_detail, name='super_order_detail'),
path('orders/export/', views.export_orders, name='super_export_orders'),
]