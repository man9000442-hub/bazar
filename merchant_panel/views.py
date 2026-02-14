from django.shortcuts import render, redirect
from django.shortcuts import  get_object_or_404
from django.contrib.auth.decorators import login_required
from store.models import Product, Order, OrderItem, Wallet
from accounts.models import User

# دالة مساعدة للتحقق من التاجر
def is_merchant(user):
    return user.role == User.Role.MERCHANT and hasattr(user, 'merchant_profile') and user.merchant_profile.is_approved

@login_required
def dashboard(request):
    if not is_merchant(request.user):
        return redirect('home') # أو صفحة خطأ

    merchant = request.user.merchant_profile
    
    # إحصائيات سريعة
    total_products = Product.objects.filter(merchant=merchant).count()
    
    # الرصيد
    try:
        balance = merchant.wallet.balance
    except:
        balance = 0

    # آخر الطلبات (التي تحتوي منتجات التاجر)
    recent_items = OrderItem.objects.filter(product_size__product__merchant=merchant).order_by('-id')[:5]

    return render(request, 'merchant/dashboard.html', {
        'total_products': total_products,
        'balance': balance,
        'recent_items': recent_items
    })

@login_required
def my_products(request):
    if not is_merchant(request.user):
        return redirect('home')
        
    products = Product.objects.filter(merchant=request.user.merchant_profile)
    return render(request, 'merchant/products.html', {'products': products})

@login_required
def merchant_orders(request):
    if not is_merchant(request.user):
        return redirect('home')
        
    # جلب العناصر المطلوبة من هذا التاجر فقط
    items = OrderItem.objects.filter(product_size__product__merchant=request.user.merchant_profile).order_by('-id')
    return render(request, 'merchant/orders.html', {'items': items})

# (سنضيف add_product لاحقاً لأنها تحتاج فورم معقد)
def add_product(request):
    return render(request, 'merchant/add_product.html') # مؤقتاً


from store.models import Category, Product, ProductSize, ProductImage

@login_required
def add_product(request):
    if not is_merchant(request.user):
        return redirect('home')

    if request.method == 'POST':
        # 1. البيانات الأساسية
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        category_id = request.POST.get('category')
        main_image = request.FILES.get('main_image')

        # إنشاء المنتج
        product = Product.objects.create(
            merchant=request.user.merchant_profile,
            name=name,
            description=description,
            base_price=price,
            category_id=category_id,
            image=main_image,
            is_active=False # ينتظر موافقة المشرف
        )

        # 2. إضافة المقاسات (Sizes)
        # البيانات تأتي كمصفوفة: sizes[], colors[], quantities[]
        sizes = request.POST.getlist('sizes[]')
        colors = request.POST.getlist('colors[]')
        quantities = request.POST.getlist('quantities[]')

        for i in range(len(sizes)):
            if sizes[i] and quantities[i]: # تأكد أن البيانات موجودة
                ProductSize.objects.create(
                    product=product,
                    size_label=sizes[i],
                    color_label=colors[i] if i < len(colors) else "Standard",
                    stock_quantity=quantities[i]
                )

        # 3. إضافة الصور الإضافية (Gallery)
        gallery_images = request.FILES.getlist('gallery_images')
        for img in gallery_images:
            ProductImage.objects.create(
                product=product,
                image=img
            )

        return redirect('merchant_products') # العودة لقائمة المنتجات

    # GET Request
    categories = Category.objects.all()
    return render(request, 'merchant/add_product.html', {'categories': categories})

from store.models import Governorate, MerchantShippingRate

@login_required
def shipping_settings(request):
    if not is_merchant(request.user):
        return redirect('home')
    
    merchant = request.user.merchant_profile
    governorates = Governorate.objects.all()

    if request.method == 'POST':
        # حفظ الأسعار
        for gov in governorates:
            price = request.POST.get(f'rate_{gov.id}') # نستقبل السعر من الـ Input
            if price:
                MerchantShippingRate.objects.update_or_create(
                    merchant=merchant,
                    governorate=gov,
                    defaults={'rate': price}
                )
        return redirect('merchant_dashboard')

    # جلب الأسعار الحالية لعرضها في الفورم
    current_rates = {rate.governorate_id: rate.rate for rate in merchant.shipping_rates.all()}
    
    return render(request, 'merchant/shipping_settings.html', {
        'governorates': governorates,
        'current_rates': current_rates
    })

@login_required
def merchant_order_detail(request, order_id):
    if not is_merchant(request.user):
        return redirect('home')
    
    # 1. جلب الطلب
    order = get_object_or_404(Order, order_id=order_id)
    
    # 2. جلب المنتجات الخاصة بهذا التاجر فقط داخل الطلب
    my_items = OrderItem.objects.filter(
        order=order, 
        product_size__product__merchant=request.user.merchant_profile
    )
    
    # حماية: لو التاجر ملوش منتجات في الطلب ده، ملوش حق يشوفه
    if not my_items.exists():
        return redirect('merchant_orders')

    return render(request, 'merchant/order_detail.html', {
        'order': order,
        'items': my_items
    })


from store.models import WalletTransaction

@login_required
def merchant_wallet(request):
    if not is_merchant(request.user):
        return redirect('home')
    
    wallet = request.user.merchant_profile.wallet
    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
    
    return render(request, 'merchant/wallet.html', {
        'wallet': wallet,
        'transactions': transactions
    })

# (صفحة طلب السحب - سنبنيها لاحقاً)
def request_withdrawal(request):
    pass 