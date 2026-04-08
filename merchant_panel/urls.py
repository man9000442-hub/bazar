from django.urls import path
from . import views
from . import api_views
urlpatterns = [
# --- الداش بورد والأقسام ---
path('api/dashboard/', api_views.merchant_dashboard_api, name='api_merchant_dashboard'),
    path('api/categories/', api_views.merchant_categories_api, name='api_merchant_categories'),
    
    # --- المنتجات ---
    path('api/products/', api_views.merchant_products_api, name='api_merchant_products'),
    path('api/products/add/', api_views.add_product_api, name='api_merchant_add_product'),
    path('api/products/<int:product_id>/delete/', api_views.delete_product_api, name='api_merchant_delete_product'),
    path('api/products/<int:product_id>/edit/', api_views.edit_product_api, name='api_merchant_edit_product'),
    path('api/products/<int:product_id>/offer/', api_views.manage_offer_api, name='api_merchant_manage_offer'),
    
    # --- الطلبات ---
    path('api/orders/', api_views.merchant_orders_api, name='api_merchant_orders'),
    path('api/orders/<str:order_id>/', api_views.api_merchant_order_detail, name='api_merchant_order_detail'),
    path('api/orders/<str:order_id>/update/', api_views.update_order_status_api, name='api_merchant_update_order'),
    
    # --- المحفظة والماليات ---
    path('api/wallet/', api_views.merchant_wallet_api, name='api_merchant_wallet'),
    path('api/wallet/data/', api_views.api_wallet_data, name='api_wallet_data'),
    path('api/wallet/transaction/', api_views.wallet_transaction_api, name='api_merchant_wallet_transaction'),
    path('api/wallet/withdraw/', api_views.api_wallet_withdraw, name='api_wallet_withdraw'),
    path('api/wallet/deposit/', api_views.api_paymob_deposit, name='api_wallet_deposit'), 
    
    # 🔴 --- بيموب (الروابط المركزية الجديدة) --- 🔴
    # 1. مسار الـ Webhook المركزي (للتاجر والعميل) - الجندي المجهول
    path('api/payment/callback/', api_views.central_paymob_callback, name='central_paymob_callback'),
    
    # 2. مسار العودة للتطبيق (للتاجر والعميل) - موظف الاستقبال
    path('api/payment/app-return/', api_views.central_app_return, name='central_app_return'),
    
    # --- التقارير والشحن والبروفايل ---
    path('api/reports/', api_views.merchant_reports_api, name='api_merchant_reports'),
    path('api/shipping/', api_views.merchant_shipping_api, name='api_merchant_shipping'),
    path('api/profile/', api_views.merchant_profile_api, name='api_merchant_profile'),
    path('api/change-password/', api_views.change_password_api, name='api_change_password'),
#---------------------------------------------------------------------------------
path('merchant/pending-approval/', views.merchant_pending_approval, name='merchant_pending_approval'),
path('', views.dashboard, name='merchant_dashboard'),
path('products/', views.my_products, name='merchant_products'),
path('products/add/', views.add_product, name='merchant_add_product'),
path('orders/', views.merchant_orders, name='merchant_orders'),
path('shipping/', views.shipping_settings, name='merchant_shipping'),
path('orders/<str:order_id>/', views.merchant_order_detail, name='merchant_order_detail'),
path('wallet/', views.merchant_wallet, name='merchant_wallet'),
path('deposit/paymob/', views.paymob_deposit, name='paymob_deposit'),
path('deposit/callback/', views.paymob_callback, name='paymob_callback'),
path('products/offer/<int:product_id>/', views.add_offer, name='merchant_add_offer'),
path('products/edit/<int:product_id>/', views.edit_product, name='merchant_edit_product'),
path('products/delete/<int:product_id>/', views.delete_product, name='merchant_delete_product'),
path('offer/cancel/<int:offer_id>/', views.cancel_offer, name='merchant_cancel_offer'),
path('orders/update/<str:order_id>/', views.update_order_status, name='merchant_update_order'),
path('withdraw/', views.request_withdrawal, name='merchant_request_withdrawal'),
path('reports/', views.merchant_reports, name='merchant_reports'),
]

#https://elbazaare.com/merchant/api/wallet/paymob-callback/