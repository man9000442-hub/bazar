from django.urls import path
from . import views

urlpatterns = [
    path('', views.supervisor_dashboard, name='supervisor_dashboard'),
    
    # Orders
    path('orders/all/', views.all_orders, name='super_all_orders'),
    path('orders/<str:order_id>/', views.order_detail, name='super_order_detail'),
    path('orders/export/', views.export_orders, name='super_export_orders'),

    # Products
    path('products/pending/', views.pending_products, name='super_pending_products'),
    path('products/review/<int:pk>/', views.product_review, name='super_product_review'),

    # Merchants
    path('merchants/pending/', views.pending_merchants, name='super_pending_merchants'),
    path('merchants/approve/<int:pk>/', views.approve_merchant, name='super_approve_merchant'),

    # Users
    path('users/', views.users_list, name='super_users_list'),
    path('users/edit/<int:user_id>/', views.user_edit, name='super_user_edit'),
    path('users/delete/<int:user_id>/', views.user_delete, name='super_user_delete'),

    # Finance
    path('deposits/pending/', views.pending_deposits, name='super_pending_deposits'),
    path('deposits/approve/<int:pk>/', views.approve_deposit, name='super_approve_deposit'),
    path('withdrawals/pending/', views.pending_withdrawals, name='super_pending_withdrawals'),
    path('withdrawals/approve/<int:pk>/', views.approve_withdrawal, name='super_approve_withdrawal'),

    # Settings & Others
    path('categories/', views.manage_categories, name='super_categories'),
    path('categories/delete/<int:pk>/', views.delete_category, name='super_delete_category'),
    path('settings/', views.site_settings_view, name='super_site_settings'),
    path('offers/create/', views.create_platform_offer, name='super_create_offer'),
    path('team/', views.team_management, name='super_team'),
    path('finance/overview/', views.finance_overview, name='super_finance_overview'),
    path('finance/logs/', views.finance_logs, name='super_finance_logs'),
    path('finance/export/profits/', views.export_profit_report, name='super_export_profits'),
    path('finance/export/debts/', views.export_debts_report, name='super_export_debts'),
    path('withdrawals/reject/<int:pk>/', views.reject_withdrawal, name='super_reject_withdrawal'),
    path('wallets/', views.wallets_list, name='super_wallets_list'),
    path('wallets/adjust/<int:wallet_id>/', views.adjust_wallet, name='super_adjust_wallet'),
]