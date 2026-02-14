from django.contrib import admin
from .models import (
    MerchantProfile, Product, ProductSize, ProductImage, 
    Wallet, WalletTransaction, Order, OrderItem,Category
)

# 1. Inlines للمنتج (صور + مقاسات)
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 1
    fields = ('size_label', 'color_label', 'stock_quantity')

# 2. إعدادات أدمن المنتج
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductSizeInline, ProductImageInline] # الـ Inlines توضع هنا فقط
    list_display = ('name', 'merchant', 'base_price', 'is_active')
    list_filter = ('is_active',)

# 3. إعدادات أدمن التاجر
@admin.register(MerchantProfile)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ('user', 'national_id', 'is_approved')
    list_filter = ('is_approved',)
    # لا تضع Inlines هنا إلا إذا كانت مرتبطة بالتاجر مباشرة

# 4. Inlines للطلب
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ('product_size', 'quantity', 'price_at_purchase', 'commission', 'merchant')
    readonly_fields = ('price_at_purchase', 'merchant')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer', 'final_total', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_id', 'customer__username', 'shipping_phone')
    inlines = [OrderItemInline]
    readonly_fields = ('order_id', 'created_at')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    
# 5. تسجيل باقي الموديلات
admin.site.register(Wallet)
admin.site.register(WalletTransaction)