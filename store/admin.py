from django.contrib import admin
from django.utils.html import format_html
from .models import (
    MerchantProfile, Product, ProductSize, ProductImage, 
    Wallet, WalletTransaction, Order, OrderItem, 
    Category, Governorate, MerchantShippingRate,
    Offer, Favorite, DepositRequest, WalletDepositTransaction, Notification,SiteSetting
)

# ----------------------------------------
# 1. Product Admin (المنتجات)
# ----------------------------------------
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductSizeInline, ProductImageInline]
    list_display = ('name', 'merchant', 'base_price', 'category', 'is_active_colored')
    list_filter = ('is_active', 'category', 'merchant')
    search_fields = ('name', 'merchant__user__username')
    actions = ['approve_products', 'deactivate_products']

    @admin.action(description='تفعيل المنتجات المختارة')
    def approve_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"تم تفعيل {updated} منتج.")

    @admin.action(description='تعطيل المنتجات المختارة')
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"تم تعطيل {updated} منتج.")

    def is_active_colored(self, obj):
        return obj.is_active
    is_active_colored.boolean = True
    is_active_colored.short_description = "نشط"


# ----------------------------------------
# 2. Order Admin (الطلبات)
# ----------------------------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    # نجعل الحقول للقراءة فقط لمنع التلاعب بالتاريخ، إلا إذا كنت تريد تعديلها يدوياً
    readonly_fields = ('product_size', 'quantity', 'price_at_purchase', 'merchant')
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer_name', 'phone', 'final_total', 'status_colored', 'created_at')
    list_filter = ('status', 'created_at', 'governorate')
    search_fields = ('order_id', 'shipping_phone', 'customer__username', 'customer__phone_primary')
    readonly_fields = ('order_id', 'created_at', 'shipping_cost', 'platform_fees', 'total_products_price', 'final_total')
    inlines = [OrderItemInline]

    def customer_name(self, obj):
        return f"{obj.customer.first_name} {obj.customer.last_name}"
    customer_name.short_description = "العميل"

    def phone(self, obj):
        return obj.shipping_phone
    phone.short_description = "الهاتف"

    def status_colored(self, obj):
        colors = {
            'PENDING': 'orange',
            'APPROVED': 'blue',
            'SHIPPED': 'purple',
            'DELIVERED': 'green',
            'CANCELLED': 'red',
            'RETURNED': 'red',
            'CART': 'gray',
        }
        color = colors.get(obj.status, 'black')
        
        # الطريقة الصحيحة لاستخدام format_html (تمرير المتغيرات كـ args)
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    
    status_colored.short_description = "الحالة"

# ----------------------------------------
# 3. Merchant & Wallet Admin (التجار والمحفظة)
# ----------------------------------------
@admin.register(MerchantProfile)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_approved', 'minimum_balance_required')
    list_filter = ('is_approved',)
    search_fields = ('user__username', )

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('merchant', 'balance', 'updated_at')
    search_fields = ('merchant__user__username',)

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'amount', 'transaction_type', 'related_order_id', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('related_order_id', 'wallet__merchant__user__username')


# ----------------------------------------
# 4. Deposit Requests (طلبات الشحن)
# ----------------------------------------
@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = ('merchant', 'amount', 'status', 'created_at')
    list_filter = ('status',)
    actions = ['approve_deposits']

    @admin.action(description='الموافقة على الطلبات المختارة')
    def approve_deposits(self, request, queryset):
        # ملاحظة: الـ Signal سيعمل تلقائياً عند الحفظ، لذا نستخدم save() في Loop
        # update() لا تطلق Signals
        for req in queryset:
            if req.status != 'APPROVED':
                req.status = 'APPROVED'
                req.save()
        self.message_user(request, "تمت الموافقة وتحديث الأرصدة.")


# ----------------------------------------
# 5. Other Models (باقي الجداول)
# ----------------------------------------
admin.site.register(Category)
admin.site.register(Governorate)
admin.site.register(MerchantShippingRate)
admin.site.register(Offer)
admin.site.register(Favorite)
admin.site.register(WalletDepositTransaction)
admin.site.register(Notification)
admin.site.register(SiteSetting)


from django.contrib import admin
from .models import PromoPopup
from django.utils import timezone

from django.contrib import admin
from django.utils import timezone
from .models import PromoPopup

@admin.register(PromoPopup)
class PromoPopupAdmin(admin.ModelAdmin):
    # غيرنا الحقول اللي بتتعرض عشان تناسب التعديلات الجديدة
    list_display = ['title', 'offer', 'is_active', 'start_time', 'end_time', 'is_currently_running']
    list_editable = ['is_active'] 
    
    # دالة ذكية تظهر علامة صح أو خطأ لو الإعلان شغال دلوقتي فعلاً
    def is_currently_running(self, obj):
        now = timezone.now()
        if obj.is_active and obj.start_time and obj.end_time:
            # شغال لو هو متفعل، ووقت البداية جه، ووقت النهاية لسه مجاش
            return obj.start_time <= now < obj.end_time
        return False
    is_currently_running.boolean = True
    is_currently_running.short_description = "يظهر للعملاء الآن؟"


