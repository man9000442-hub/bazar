from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('add-to-cart/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart_view'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:item_id>/<str:action>/', views.update_cart_qty, name='update_cart_qty'),
    path('checkout/', views.checkout, name='checkout'),
    path('order-success/', views.order_success, name='order_success'),
    path('api/calc-shipping/', views.calculate_shipping_api, name='calc_shipping_api'),
    path('categories/', views.categories_page, name='categories_page'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('confirm-delivery/<int:order_id>/', views.confirm_delivery_view, name='confirm_delivery_view'),
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('payment/retry/<int:order_id>/', views.retry_payment, name='retry_payment'),
    path('my-orders/<int:order_id>/', views.customer_order_detail, name='customer_order_detail'),
    path('shop/<int:merchant_id>/', views.merchant_shop, name='merchant_shop'),
]