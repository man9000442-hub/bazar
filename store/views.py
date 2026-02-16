from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Product, Category, Order, OrderItem, ProductSize, Governorate,MerchantShippingRate
from django.db.models import F
from django.db.models import Q
import json
from .models import Notification


def check_pending_confirmations(user):
    """
    دالة تفحص هل يوجد طلبات (تم تسليمها) لكن العميل لم يؤكدها أو يرفضها بعد.
    ترجع الطلب المعلق إن وجد، أو None.
    """
    if not user.is_authenticated: return None
    
    # نبحث عن طلب حالته DELIVERED ولكن العميل لم يؤكده (is_confirmed_by_customer is None)
    pending = Order.objects.filter(
        customer=user, 
        status=Order.Status.DELIVERED, 
        is_confirmed_by_customer__isnull=True
    ).first()
    return pending

# صفحة التأكيد الإجبارية
# صفحة تأكيد الاستلام (Blocker)
@login_required
def confirm_delivery_view(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirm':
            order.is_confirmed_by_customer = True
            # order.rating = ...
            messages.success(request, "شكراً لتأكيدك!")
        elif action == 'reject':
            order.is_confirmed_by_customer = False
            order.status = Order.Status.RETURNED # أو نزاع
            messages.warning(request, "تم تسجيل الشكوى.")
            
        order.save()
        return redirect('home')

    return render(request, 'store/confirm_delivery.html', {'order': order})


# الصفحة الرئيسية
def home(request):
    pending_conf = check_pending_confirmations(request.user)
    if pending_conf:
        # توجيه إجباري لصفحة التأكيد
        return redirect('confirm_delivery_view', order_id=pending_conf.id)
    if request.user.is_authenticated:
        if not request.user.phone_primary:
            return redirect('complete_profile')
    query = request.GET.get('q') # كلمة البحث
    category_id = request.GET.get('category')
    products = Product.objects.filter(
        is_active=True,
        merchant__wallet__balance__gte=F('merchant__minimum_balance_required')
    ).order_by('-created_at')


    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query)
        )

    if category_id:
        products = products.filter(category_id=category_id)
    
    products = products.order_by('-created_at')
    categories = Category.objects.all()
    offers = Product.objects.filter(
        active_offer__is_active=True,
        active_offer__end_date__gte=timezone.now(),
        is_active=True # المنتج نفسه لازم يكون مفعل
    ).order_by('-active_offer__discount_percentage')[:5] # نأخذ أقوى 5 عروض

    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    return render(request, 'store/home.html', {
        'products': products,
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
        'search_query': query,
        'offers': offers,
        'unread_notifications_count': unread_count # لإبقائها في مربع البحث
    })

# تفاصيل المنتج
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    sizes = product.variations.filter(stock_quantity__gt=0)
    return render(request, 'store/product_detail.html', {'product': product, 'sizes': sizes})

# إضافة للسلة (مع رسائل تتبع Debug)
@login_required
def add_to_cart(request, pk):
    print("--- 1. Add to cart function called ---") 
    
    if request.method == 'POST':
        size_id = request.POST.get('size_id')
        quantity = request.POST.get('quantity', 1)
        
        # التحقق من اختيار المقاس
        if not size_id:
            messages.error(request, "الرجاء اختيار المقاس واللون.")
            return redirect('product_detail', pk=pk)

        product_size = get_object_or_404(ProductSize, pk=size_id)
        product = product_size.product # المنتج الأصلي
        quantity = int(quantity)

        # التحقق من المخزون
        if quantity > product_size.stock_quantity:
            messages.error(request, "الكمية المطلوبة غير متوفرة.")
            return redirect('product_detail', pk=pk)

        # ==========================================
        # 1. تحديد السعر (هل يوجد عرض نشط؟)
        # ==========================================
        final_price = product.base_price # السعر الافتراضي

        try:
            # نحاول الوصول للعرض المرتبط بالمنتج
            offer = product.active_offer
            # الشرط: العرض موجود + مفعل + تاريخه ساري
            if offer and offer.is_active:
                from django.utils import timezone
                if offer.end_date >= timezone.now():
                    final_price = offer.discounted_price
                    print(f"--- Offer Applied: New Price is {final_price} ---")
        except:
            pass # لا يوجد عرض أو حدث خطأ بسيط

        # ==========================================
        # 2. إنشاء أو جلب الطلب (Sart)
        # ==========================================
        order, created = Order.objects.get_or_create(
            customer=request.user,
            status=Order.Status.CART, 
            defaults={
                'total_products_price': 0, 
                'final_total': 0,
                'shipping_address': 'مؤقت', 
                'shipping_phone': request.user.phone_primary
            }
        )

        # ==========================================
        # 3. إضافة المنتج للسلة بالسعر الصحيح
        # ==========================================
        order_item, item_created = OrderItem.objects.get_or_create(
            order=order,
            product_size=product_size,
            defaults={
                'quantity': quantity,
                'price_at_purchase': final_price, # <--- السعر النهائي (مخفض أو أصلي)
                'merchant': product.merchant
            }
        )

        if not item_created:
            # لو المنتج كان موجوداً، نحدث الكمية والسعر (لأن العرض قد يكون تغير)
            order_item.quantity += quantity
            order_item.price_at_purchase = final_price 
            order_item.save()
            print("--- Quantity & Price Updated ---")
        
        # حفظ الطلب لتفعيل الـ Signal وتحديث الإجمالي
        order.save()

        messages.success(request, "تمت الإضافة للسلة بنجاح! 🛍️")
        return redirect('home')

    return redirect('home')

# عرض السلة
@login_required
def cart_view(request):
    order = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    return render(request, 'store/cart.html', {'order': order})

# حذف من السلة
@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__customer=request.user, order__status=Order.Status.CART)
    item.delete()
    return redirect('cart_view')

# تحديث الكمية
@login_required
def update_cart_qty(request, item_id, action):
    item = get_object_or_404(OrderItem, id=item_id, order__customer=request.user, order__status=Order.Status.CART)
    if action == 'add':
        if item.quantity < item.product_size.stock_quantity:
            item.quantity += 1
            item.save()
    elif action == 'sub':
        if item.quantity > 1:
            item.quantity -= 1
            item.save()
        else:
            item.delete()
    return redirect('cart_view')

# إتمام الطلب (Checkout)
from collections import defaultdict

@login_required
def checkout(request):
    # ... (فحص المانع أولاً) ...
    pending_conf = check_pending_confirmations(request.user)
    if pending_conf: return redirect('confirm_delivery_view', order_id=pending_conf.id)

    # جلب السلة
    cart = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not cart or not cart.items.exists():
        return redirect('home')

    governorates = Governorate.objects.all()

    # --- تجهيز البيانات للعرض (Grouping by Merchant) ---
    grouped_items = defaultdict(list)
    merchant_totals = defaultdict(int) # لحساب مجموع منتجات كل تاجر
    
    for item in cart.items.all():
        merch = item.product_size.product.merchant
        grouped_items[merch].append(item)
        merchant_totals[merch] += item.total_price # تأكد أن OrderItem لديه property total_price

    # تحويلها لقائمة ليسهل عرضها في التمبلت
    cart_structure = []
    for merch, items in grouped_items.items():
        cart_structure.append({
            'merchant': merch,
            'items': items,
            'subtotal': merchant_totals[merch]
        })

    # --- معالجة الـ POST (إنشاء الطلبات الحقيقية) ---
    if request.method == 'POST':
        address = request.POST.get('address')
        gov_id = request.POST.get('city')
        phone = request.POST.get('phone')
        
        gov = get_object_or_404(Governorate, pk=gov_id)
        
        # 1. هل هذا أول طلب للعميل؟ (للشحن المجاني)
        is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
        free_shipping_used = False # عشان نطبق المجاني مرة واحدة بس

        # 2. اللوب الجهنمية (إنشاء طلب لكل تاجر) 🔥
        for group in cart_structure:
            merchant = group['merchant']
            items = group['items']
            
            # أ. حساب شحن هذا التاجر لهذه المحافظة
            shipping_rate = MerchantShippingRate.objects.filter(merchant=merchant, governorate=gov).first()
            shipping_cost = shipping_rate.rate if shipping_rate else 50 # افتراضي
            
            # ب. تطبيق الشحن المجاني (لأول تاجر فقط في اللوب)
            if is_first_order and not free_shipping_used:
                shipping_cost = 0
                free_shipping_used = True
                # (هنا ممكن نسجل في Log إن التاجر ده ليه تعويض شحن عند الإدارة)

            # ج. إنشاء الطلب الجديد الخاص بالتاجر
            new_order = Order.objects.create(
                customer=request.user,
                merchant=merchant, # ربطنا الطلب بالتاجر
                shipping_address=f"{gov.name} - {address}",
                governorate=gov,
                shipping_phone=phone,
                status=Order.Status.PENDING,
                # الأرقام سيتم حسابها بالـ Signal لما ننقل المنتجات
                shipping_cost=shipping_cost,
                is_first_order=(shipping_cost == 0) # علامة إن الشحن مجاني
            )
            
            # د. نقل المنتجات من السلة للطلب الجديد
            for item in items:
                item.order = new_order # تغيير الأب
                item.save() # الـ Signal هيشتغل ويحسب مجاميع الطلب الجديد
            
            # هـ. الـ Signal في OrderItem هيحدث new_order
            new_order.save() 

        # 3. حذف السلة القديمة (لأنها فضيت خلاص)
        cart.delete()
        
        messages.success(request, "تم تقسيم الطلبات وإرسالها للتجار بنجاح! 🎉")
        return redirect('my_orders') # نوديه لصفحة طلباتي يشوفهم

    return render(request, 'store/checkout.html', {
        'cart_structure': cart_structure, # الهيكل المقسم
        'governorates': governorates,
        'cart_total': cart.total_products_price, # مجرد رقم للعرض
        'platform_fees': cart.platform_fees
    })


from django.http import JsonResponse # مهم

@login_required
def calculate_shipping_api(request):
    gov_id = request.GET.get('gov_id')
    if not gov_id: return JsonResponse({'error': 'No ID'}, status=400)

    cart = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not cart: return JsonResponse({'shipping_details': [], 'total_shipping': 0, 'grand_total': 0})

    governorate = get_object_or_404(Governorate, pk=gov_id)
    
    # 1. تجميع التجار
    merchants = set(item.product_size.product.merchant for item in cart.items.all())
    
    shipping_details = []
    total_shipping = 0
    
    # 2. فحص الشحن المجاني (أول مرة)
    is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
    free_shipping_used = False

    for merchant in merchants:
        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=governorate).first()
        cost = rate_obj.rate if rate_obj else 50
        
        # تطبيق المجاني
        if is_first_order and not free_shipping_used:
            cost = 0
            free_shipping_used = True
            
        total_shipping += cost
        shipping_details.append({
            'merchant_id': merchant.id,
            'cost': float(cost)
        })

    # الإجمالي النهائي المتوقع
    grand_total = float(cart.total_products_price + cart.platform_fees) + float(total_shipping)

    return JsonResponse({
        'shipping_details': shipping_details, # قائمة {تاجر: سعر}
        'total_shipping': float(total_shipping),
        'grand_total': grand_total
    })

# صفحة النجاح (تظهر بعد إتمام الطلب)
def order_success(request):
    return render(request, 'store/order_success.html')

def categories_page(request):
    categories = Category.objects.all()
    return render(request, 'store/categories.html', {'categories': categories})


@login_required
def my_orders(request):
    # نستبعد حالة السلة (CART)
    orders = Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).order_by('-created_at')
    return render(request, 'store/my_orders.html', {'orders': orders})



from django.http import JsonResponse
from .models import Favorite

# 1. زر التبديل (أضف/احذف) باستخدام AJAX لكي لا يعيد تحميل الصفحة
@login_required
def toggle_favorite(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
    
    if not created:
        # إذا كان موجوداً بالفعل -> احذفه
        favorite.delete()
        added = False
    else:
        # تم إنشاؤه -> يعني تمت الإضافة
        added = True
    
    return JsonResponse({'added': added, 'count': request.user.favorites.count()})

# 2. صفحة عرض المفضلة
@login_required
def wishlist_view(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('product')
    return render(request, 'store/wishlist.html', {'favorites': favorites})



import json # استيراد json

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    
    # جلب كل المتغيرات المتاحة
    variations = product.variations.filter(stock_quantity__gt=0)
    
    # تجميع الألوان المتاحة (بدون تكرار)
    available_colors = set(v.color_label for v in variations)
    
    # بناء قاموس: { 'أحمر': [ {id: 1, size: 'XL'}, {id: 2, size: 'L'} ], ... }
    variants_data = {}
    for v in variations:
        if v.color_label not in variants_data:
            variants_data[v.color_label] = []
        variants_data[v.color_label].append({
            'id': v.id,
            'size': v.size_label,
            'qty': v.stock_quantity
        })

    # تحويل القاموس لنص JSON لنستخدمه في الجافاسكربت
    variants_json = json.dumps(variants_data)

    # ... (باقي الكود: منتجات مشابهة، مفضلة) ...
    # (نفس الكود السابق للمنتجات المشابهة والمفضلة)
    similar_products = Product.objects.filter(category=product.category, is_active=True).exclude(pk=pk)[:4]
    is_fav = False
    if request.user.is_authenticated:
        is_fav = Favorite.objects.filter(user=request.user, product=product).exists()

    return render(request, 'store/product_detail.html', {
        'product': product,
        'available_colors': available_colors,
        'variants_json': variants_json, # البيانات الجديدة
        'similar_products': similar_products,
        'is_fav': is_fav
    })



@login_required
def notifications_view(request):
    # جلب إشعارات المستخدم (الأحدث أولاً)
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    
    # عند فتح الصفحة، نجعل كل الإشعارات "مقروءة"
    # (أو يمكنك جعلها مقروءة عند الضغط على رابط الإشعار - سنفعل الأسهل الآن)
    notifications.filter(is_read=False).update(is_read=True)
    
    return render(request, 'store/notifications.html', {'notifications': notifications})