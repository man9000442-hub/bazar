from django.urls import path
from . import views
urlpatterns = [

#=====================================================================

    path('merchant/pending-approval/', views.merchant_pending_approval, name='merchant_pending_approval'),
    path('', views.dashboard, name='merchant_dashboard'),
    path('products/', views.my_products, name='merchant_products'),
    path('products/add/', views.add_product, name='merchant_add_product'),
    path('orders/', views.merchant_orders, name='merchant_orders'),
    path('shipping/', views.shipping_settings, name='merchant_shipping'),
    path('orders/<str:order_id>/', views.merchant_order_detail, name='merchant_order_detail'),
    path('wallet/', views.merchant_wallet, name='merchant_wallet'),
    path('deposit/online/', views.charge_wallet_online, name='paymob_deposit'),
    path('products/offer/<int:product_id>/', views.add_offer, name='merchant_add_offer'),
    path('products/edit/<int:product_id>/', views.edit_product, name='merchant_edit_product'),
    path('products/delete/<int:product_id>/', views.delete_product, name='merchant_delete_product'),
    path('offer/cancel/<int:offer_id>/', views.cancel_offer, name='merchant_cancel_offer'),
    path('orders/update/<str:order_id>/', views.update_order_status, name='merchant_update_order'),
    path('withdraw/', views.request_withdrawal, name='merchant_request_withdrawal'),
    path('reports/', views.merchant_reports, name='merchant_reports'),
]

#https://elbazaare.com/merchant/api/wallet/paymob-callback/