from rest_framework import serializers
from .models import Product, Order, OrderItem, Category

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product_size.product.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'quantity', 'price_at_purchase']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Order
        fields = ['order_id', 'final_total', 'status', 'created_at', 'items']