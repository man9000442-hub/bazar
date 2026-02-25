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
    path('products/all/', views.all_products, name='super_all_products'),
path('products/delete/<int:pk>/', views.delete_product_admin, name='super_delete_product'),
path('products/edit/<int:pk>/', views.edit_product_admin, name='super_edit_product'),
path('support/', views.support_tickets, name='super_support_tickets'),
path('support/<int:pk>/', views.support_ticket_detail, name='super_ticket_detail'),
path('team/roles/', views.manage_roles, name='super_manage_roles'),
path('team/roles/delete/<int:pk>/', views.delete_role, name='super_delete_role'),
path('offers/', views.manage_offers, name='super_manage_offers'),
path('offers/delete/<int:pk>/', views.delete_offer_admin, name='super_delete_offer'),
path('notifications/send/', views.send_broadcast, name='super_send_broadcast'),
path('users/banned/', views.banned_users, name='super_banned_users'),
path('users/ban/<int:user_id>/', views.ban_user, name='super_ban_user'),
path('analytics/customers/', views.customers_analytics, name='super_customers_analytics'),
path('analytics/customer/<int:user_id>/', views.customer_profile_admin, name='super_customer_profile'),
path('banners/', views.manage_banners, name='super_manage_banners'),
path('banners/delete/<int:pk>/', views.delete_banner, name='super_delete_banner'),
    # Terms & Conditions
    path('terms/', views.manage_terms, name='super_manage_terms'),
    path('terms/delete/<int:pk>/', views.delete_term, name='super_delete_term'),
    path('merchants/reject/<int:pk>/', views.reject_merchant, name='super_reject_merchant'),
    path('merchants/all/', views.merchants_list, name='super_merchants_list'),
path('merchants/profile/<int:pk>/', views.merchant_profile_admin, name='super_merchant_profile'),
]