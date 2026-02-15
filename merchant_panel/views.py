from django.shortcuts import render, redirect
from django.shortcuts import  get_object_or_404
from django.contrib.auth.decorators import login_required
from store.models import Product, Order, OrderItem, Wallet
from accounts.models import User
from django.contrib import messages
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

    # 1. معالجة الحفظ (POST) - (كما هي لم تتغير)
    if request.method == 'POST':
        for gov in governorates:
            input_name = f'rate_{gov.id}'
            price = request.POST.get(input_name)
            
            if not price or float(price) == 0:
                MerchantShippingRate.objects.filter(merchant=merchant, governorate=gov).delete()
            else:
                MerchantShippingRate.objects.update_or_create(
                    merchant=merchant,
                    governorate=gov,
                    defaults={'rate': price}
                )
        messages.success(request, "تم حفظ أسعار الشحن بنجاح ✅")
        return redirect('merchant_shipping')

    # 2. تجهيز البيانات للعرض (GET) - (هنا التعديل لإصلاح الخطأ)
    
    # جلب الأسعار الحالية في قاموس
    current_rates_dict = {rate.governorate_id: rate.rate for rate in merchant.shipping_rates.all()}
    
    # دمج المحافظة مع سعرها في قائمة واحدة
    shipping_data = []
    for gov in governorates:
        shipping_data.append({
            'id': gov.id,
            'name': gov.name,
            # إذا كان هناك سعر نضعه، وإلا نترك القيمة فارغة
            'current_rate': current_rates_dict.get(gov.id, '') 
        })
    
    return render(request, 'merchant/shipping_settings.html', {
        'shipping_data': shipping_data # نرسل القائمة الجديدة بدلاً من القديمة
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


from django.http import HttpResponse
from store.paymob_utils import PaymobManager
from store.models import PaymobTransaction, WalletTransaction, Wallet
from django.conf import settings

# 1. صفحة طلب الشحن (يختار المبلغ وطريقة الدفع)
@login_required
def paymob_deposit(request):
    if not is_merchant(request.user):
        return redirect('home')

    if request.method == 'POST':
        amount = float(request.POST.get('amount'))
        amount_cents = int(amount * 100) # Paymob يتعامل بالقروش
        
        # بيانات وهمية للفوترة (مطلوبة من Paymob)
        user = request.user
        billing_data = {
            "first_name": user.first_name or "Merchant",
            "last_name": user.last_name or "User",
            "email": user.email,
            "phone_number": user.phone_primary,
            "apartment": "NA", "email": user.email, "floor": "NA", 
            "street": "NA", "building": "NA", "shipping_method": "NA", 
            "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
        }

        # --- بدء التعامل مع Paymob ---
        paymob = PaymobManager()
        token = paymob.get_token()
        order_id = paymob.create_order(token, amount_cents)
        
        # تسجيل المعاملة في الداتابيز عندنا
        PaymobTransaction.objects.create(
            merchant=request.user.merchant_profile,
            paymob_order_id=order_id,
            amount_cents=amount_cents
        )

        # الحصول على Payment Key (للكروت حالياً كمثال)
        # يمكنك إضافة شرط لو اختار محفظة تستخدم Integration ID آخر
        integration_id = settings.PAYMOB_INTEGRATION_ID_CARD 
        payment_key = paymob.get_payment_key(token, order_id, amount_cents, integration_id, billing_data)

        # التوجيه لصفحة الدفع (Iframe)
        iframe_id = settings.PAYMOB_IFRAME_ID
        return redirect(f"https://accept.paymob.com/api/acceptance/iframes/{iframe_id}?payment_token={payment_key}")

    return render(request, 'merchant/paymob_deposit.html')


# 2. Callback (الصفحة التي يعود لها التاجر بعد الدفع)
def paymob_callback(request):
    # Paymob بيرسل البيانات في الـ GET params
    success = request.GET.get('success')
    order_id = request.GET.get('order') # Paymob Order ID
    
    if success == "true":
        try:
            # البحث عن المعاملة عندنا
            tx = PaymobTransaction.objects.get(paymob_order_id=order_id, is_paid=False)
            
            # تحديث الحالة
            tx.is_paid = True
            tx.save()
            
            # --- إضافة الرصيد للمحفظة ---
            wallet = tx.merchant.wallet
            amount_egp = tx.amount_cents / 100
            
            WalletTransaction.objects.create(
                wallet=wallet,
                amount=amount_egp,
                transaction_type=WalletTransaction.TxType.COMPENSATION, # أو نوع جديد DEPOSIT
                description=f"شحن رصيد (Paymob) #{tx.id}",
                balance_after=wallet.balance + Decimal(amount_egp)
            )
            
            wallet.balance += Decimal(amount_egp)
            wallet.save()
            
            messages.success(request, "تم شحن الرصيد بنجاح! 🎉")
            return redirect('merchant_wallet')
            
        except PaymobTransaction.DoesNotExist:
            # قد تكون دفعت وسجلت بالفعل (تكرار الريكوست)
            return redirect('merchant_wallet')
    else:
        messages.error(request, "عملية الدفع فشلت أو تم إلغاؤها.")
        return redirect('merchant_wallet')