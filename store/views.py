from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Product, Category, Order, OrderItem, ProductSize, Governorate,MerchantShippingRate
from django.db.models import F
from django.db.models import Q
# الصفحة الرئيسية
def home(request):
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

    return render(request, 'store/home.html', {
        'products': products,
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
        'search_query': query # لإبقائها في مربع البحث
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
        
        print(f"--- 2. Data received: Size ID={size_id}, Qty={quantity}") 
        
        if not size_id:
            messages.error(request, "الرجاء اختيار المقاس.")
            return redirect('product_detail', pk=pk)

        product_size = get_object_or_404(ProductSize, pk=size_id)
        quantity = int(quantity)

        if quantity > product_size.stock_quantity:
            messages.error(request, "الكمية غير متوفرة.")
            return redirect('product_detail', pk=pk)

        # البحث عن أو إنشاء الطلب (حالة CART)
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
        print(f"--- 4. Order Info: ID={order.id}, Status={order.status}, Created={created}")

        # إضافة المنتج
        order_item, item_created = OrderItem.objects.get_or_create(
            order=order,
            product_size=product_size,
            defaults={
                'quantity': quantity,
                'price_at_purchase': product_size.product.base_price,
                'merchant': product_size.product.merchant
            }
        )
        print(f"--- 5. Item Info: Created={item_created}")

        if not item_created:
            order_item.quantity += quantity
            order_item.save()
            print("--- 6. Quantity Updated ---")
        
        # مهم: نقوم بعمل save للطلب لتفعيل الـ Signal وتحديث الأسعار
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
@login_required
def checkout(request):
    # 1. جلب السلة (CART)
    # إذا تحولت الحالة بالخطأ لـ PENDING سابقاً، هذا السطر لن يجد الطلب وسيعيدك للرئيسية
    order = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    
    # حماية: لو السلة فاضية أو مش موجودة، ارجع للرئيسية
    if not order or order.items.count() == 0:
        return redirect('home')

    # جلب المحافظات للعرض
    governorates = Governorate.objects.all()

    # 2. هل العميل ضغط على زر التأكيد؟ (POST)
    if request.method == 'POST':
        # --- هنا فقط نبدأ التعديل والحفظ ---
        
        address = request.POST.get('address')
        gov_id = request.POST.get('city')
        phone = request.POST.get('phone')

        if not (address and gov_id and phone):
            messages.error(request, "يرجى ملء جميع البيانات")
            return redirect('checkout')

        governorate = get_object_or_404(Governorate, pk=gov_id)

        # تحديث البيانات
        order.shipping_address = f"{governorate.name} - {address}"
        order.governorate = governorate
        order.shipping_phone = phone
        
        # حساب الشحن النهائي
        total_shipping = 0
        merchants = set(item.product_size.product.merchant for item in order.items.all())
        for merchant in merchants:
            rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=governorate).first()
            if rate_obj:
                total_shipping += rate_obj.rate
            else:
                total_shipping += 50
        
        order.shipping_cost = total_shipping
        
        # ⚠️ اللحظة الحاسمة: هنا فقط نغير الحالة
        order.status = Order.Status.PENDING 
        order.created_at = timezone.now()
        order.save()
        
        messages.success(request, "تم استلام طلبك بنجاح!")
        return redirect('order_success')

    # 3. مجرد عرض الصفحة (GET)
    # ⚠️ لا نكتب أي كود save() أو تغيير status هنا أبداً
    return render(request, 'store/checkout.html', {
        'order': order,
        'governorates': governorates
    })


from django.http import JsonResponse # مهم

@login_required
def calculate_shipping_api(request):
    """
    API تستقبل ID المحافظة، وتحسب الشحن بناءً على التجار في السلة.
    ترجع JSON: { 'shipping': 50, 'total': 150 }
    """
    gov_id = request.GET.get('gov_id')
    if not gov_id:
        return JsonResponse({'error': 'No ID'}, status=400)

    # 1. جلب السلة
    order = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not order:
        return JsonResponse({'shipping': 0, 'total': 0})

    # 2. جلب المحافظة
    governorate = get_object_or_404(Governorate, pk=gov_id)
    
    # 3. حساب الشحن (نفس منطق الـ checkout بالضبط)
    total_shipping = 0
    merchants = set(item.product_size.product.merchant for item in order.items.all())
    
    for merchant in merchants:
        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=governorate).first()
        if rate_obj:
            total_shipping += rate_obj.rate
        else:
            total_shipping += 50 # الافتراضي

    # 4. حساب الإجمالي النهائي (للعرض)
    # ملاحظة: platform_fees محسوبة مسبقاً في الـ Order
    final_total = order.total_products_price + order.platform_fees + total_shipping

    return JsonResponse({
        'shipping': float(total_shipping),
        'total': float(final_total)
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