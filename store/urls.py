from django.urls import path
from . import views
from . import api_views
from store.sitemaps import ProductSitemap
from django.contrib.sitemaps.views import sitemap
from django.views.generic.base import TemplateView
from store.sitemaps import ProductSitemap, StaticSitemap

sitemaps = {
     'static': StaticSitemap,
     'products': ProductSitemap,
 }

urlpatterns = [
    path('', views.home, name='home'),
    path('offers/', views.all_offers_page, name='all_offers'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('set-country/', views.set_user_country, name='set_user_country'),
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
    
    #  هذا هو الرابط  (Webhook) الذي يستقبل ردود بوابات الدفع (Paymob أو Fawaterk)
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    
    path('payment/retry/<int:order_id>/', views.retry_payment, name='retry_payment'),
    path('my-orders/<int:order_id>/', views.customer_order_detail, name='customer_order_detail'),
    path('shop/<int:merchant_id>/', views.merchant_shop, name='merchant_shop'),
    path('referral-center/', views.referral_center, name='referral_center'),  
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path('legal/<str:doc_type>/<str:user_type>/', views.legal_document, name='legal_document'),
    path('about-us/', views.about_us, name='about_us'),
    path('product/<int:product_id>/submit-review/', views.submit_review, name='submit_review'),
    path('privacy-policy/', views.customer_privacy_policy, name='privacy-policy'),
    path('set-country/', views.set_user_country, name='set_country'),

    # ================= API Routes =================
    path('api/terms/customer/', api_views.api_customer_terms, name='api_customer_terms'),
    path('api/customer/home/', api_views.home_api, name='api_customer_home'),
    path('api/customer/product/<int:product_id>/', api_views.product_detail_api, name='api_customer_product_detail'),
    path('api/customer/wishlist/toggle/<int:product_id>/', api_views.toggle_favorite_api, name='api_customer_toggle_fav'),
    path('api/customer/cart/', api_views.cart_data_api, name='api_customer_cart_data'),
    path('api/customer/checkout/place-order/', api_views.place_order_api, name='api_customer_place_order'),
    path('api/customer/orders/', api_views.my_orders_api, name='api_customer_my_orders'),
    path('api/customer/orders/<int:order_id>/action/', api_views.confirm_delivery_action_api, name='api_customer_order_action'),
    path('api/customer/referral/', api_views.referral_center_api, name='api_customer_referral'),
]