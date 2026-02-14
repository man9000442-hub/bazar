from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='merchant_dashboard'),
    path('products/', views.my_products, name='merchant_products'),
    path('products/add/', views.add_product, name='merchant_add_product'),
    path('orders/', views.merchant_orders, name='merchant_orders'),
    path('shipping/', views.shipping_settings, name='merchant_shipping'),
    path('orders/<str:order_id>/', views.merchant_order_detail, name='merchant_order_detail'),
    path('wallet/', views.merchant_wallet, name='merchant_wallet'),
]