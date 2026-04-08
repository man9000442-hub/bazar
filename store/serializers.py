from rest_framework import serializers
from .models import Product, Category, Banner, Offer
from .models import Order, OrderItem, ProductSize
class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ['id', 'image', 'link']

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'image']

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    merchant_name = serializers.CharField(source='merchant.user.first_name', read_only=True, default="إلـ بازار")
    rating = serializers.FloatField(source='average_rating', read_only=True)
    
    # حقول العروض (لو المنتج عليه خصم)
    has_offer = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'base_price', 'image', 'category_name', 'merchant_name', 'rating', 'has_offer', 'final_price']

    def get_has_offer(self, obj):
        if hasattr(obj, 'active_offer') and obj.active_offer.is_currently_active:
            return True
        return False

    def get_final_price(self, obj):
        if hasattr(obj, 'active_offer') and obj.active_offer.is_currently_active:
            return obj.active_offer.discounted_price
        return obj.base_price
    
from .models import  Order, OrderItem

class CartItemSerializer(serializers.ModelSerializer):
    # نصل لاسم المنتج من خلال ProductSize
    product_name = serializers.CharField(source='product_size.product.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    total_price = serializers.DecimalField(source='total_price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product_size', 'product_name', 'product_image', 'quantity', 'price_at_purchase', 'total_price']

    def get_product_image(self, obj):
        request = self.context.get('request')
        if obj.product_size.product.image:
            # لجعل الرابط كاملاً لتطبيق فلاتر
            return request.build_absolute_uri(obj.product_size.product.image.url) if request else obj.product_size.product.image.url
        return None

class OrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    date = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'total', 'status', 'status_display', 'date', 'shipping_address']