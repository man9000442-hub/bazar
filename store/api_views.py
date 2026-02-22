from rest_framework import generics
from .models import Product, Order
from .serializers import ProductSerializer, OrderSerializer

class ProductListAPI(generics.ListAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [] # عام

class OrderListAPI(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    
    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user)