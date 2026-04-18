from django.urls import path
from . import views
from . import api_views

urlpatterns = [
# الإحصائيات المالية والعامة
    path('api/dashboard/', api_views.admin_dashboard_api, name='api_admin_dashboard'),
    path('api/finance/', api_views.finance_overview_api, name='api_finance_overview'),

    # إدارة التجار
    path('api/merchants/pending/', api_views.pending_merchants_api, name='api_pending_merchants'),
    path('api/merchants/<int:merchant_id>/approve/', api_views.approve_merchant_api, name='api_approve_merchant'),

    # إدارة المنتجات
    path('api/products/pending/', api_views.pending_products_api, name='api_pending_products'),
    path('api/products/<int:product_id>/approve/', api_views.approve_product_api, name='api_approve_product'),



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
path('owner-dashboard/', views.owner_dashboard, name='owner_dashboard'),
path('supervisor/translations/', views.system_translations_view, name='super_system_translations'),
path('categories/', views.manage_categories, name='super_categories'),
path('merchant/<int:pk>/toggle-verify/', views.toggle_verify_merchant, name='super_toggle_verify_merchant'),
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
path('terms/edit/<int:pk>/', views.edit_term, name='super_edit_term'),
path('merchants/reject/<int:pk>/', views.reject_merchant, name='super_reject_merchant'),
path('merchants/all/', views.merchants_list, name='super_merchants_list'),
path('merchants/profile/<int:pk>/', views.merchant_profile_admin, name='super_merchant_profile'),
# Settings & Others
path('categories/', views.manage_categories, name='super_categories'),
path('categories/delete/<int:pk>/', views.delete_category, name='super_delete_category'),
path('categories/edit/<int:pk>/', views.edit_category, name='super_edit_category'),
path('merchants/update-limit/<int:pk>/', views.update_merchant_limit, name='super_update_merchant_limit'),
path('merchants/hide-products/<int:pk>/', views.hide_merchant_products, name='super_hide_merchant_products'),
path('merchants/show-products/<int:pk>/', views.show_merchant_products, name='super_show_merchant_products'),
path('personal-vouchers/', views.manage_vouchers, name='super_manage_vouchers'),
path('personal-vouchers/delete/<int:pk>/', views.delete_voucher, name='super_delete_voucher'),
path('edit-about-us/', views.edit_about_us, name='super_edit_about_us'),
path('complaints/', views.admin_complaints_list, name='admin_complaints_list'),
path('complaints/resolve/<int:complaint_id>/', views.admin_resolve_complaint, name='admin_resolve_complaint'),
path('reviews/', views.super_reviews_list, name='super_reviews_list'),
path('notifications/', views.admin_notifications, name='admin_notifications'), 
path('popups/', views.super_manage_popups, name='super_manage_popups'),
path('popups/toggle/<int:pk>/', views.super_toggle_popup, name='super_toggle_popup'),
path('popups/delete/<int:pk>/', views.super_delete_popup, name='super_delete_popup'),
path('countries/', views.manage_countries, name='super_manage_countries'),
path('countries/delete/<int:pk>/', views.delete_country, name='super_delete_country'),
path('governorates/', views.manage_governorates, name='super_manage_governorates'),
path('governorates/delete/<int:pk>/', views.delete_governorate, name='super_delete_governorate'),
]