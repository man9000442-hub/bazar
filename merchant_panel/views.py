from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from django.conf import settings
from collections import defaultdict

# الموديلات (نستوردها من store لأنها معرفة هناك)
from store.models import (
    Product, ProductSize, ProductImage, Order, OrderItem, 
    Wallet, WalletTransaction, MerchantProfile, Governorate, 
    MerchantShippingRate, DepositRequest, WithdrawalRequest, 
    Offer, PaymobTransaction
)
from accounts.models import User

# دوال مساعدة
from store.paymob_utils import PaymobManager

# دالة التحقق (Helper Function)
def is_merchant(user):
    return user.role == User.Role.MERCHANT and hasattr(user, 'merchant_profile') and user.merchant_profile.is_approved
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
    recent_items = OrderItem.objects.filter(
        product_size__product__merchant=request.user.merchant_profile
    ).exclude(
        order__status__in=['CART', 'WAITING_PAYMENT'] # نكتب النصوص مباشرة أو Order.Status.CART
    ).order_by('-order__created_at')

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
    if not is_merchant(request.user): return redirect('home')
    
    # استبعاد السلة وانتظار الدفع
    excluded_statuses = [Order.Status.CART, Order.Status.WAITING_PAYMENT]
    
    items = OrderItem.objects.filter(
        product_size__product__merchant=request.user.merchant_profile
    ).exclude(
        order__status__in=excluded_statuses
    ).order_by('-order__created_at')

    return render(request, 'merchant/orders.html', {'items': items})

# (سنضيف add_product لاحقاً لأنها تحتاج فورم معقد)
def add_product(request):
    return render(request, 'merchant/add_product.html') # مؤقتاً


from store.models import Category, Product, ProductSize, ProductImage

@login_required
def add_product(request):
    if not is_merchant(request.user): return redirect('home')

    if request.method == 'POST':
        # 1. البيانات الأساسية
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        shipping_fee = request.POST.get('shipping_fee', 0)
        category_id = request.POST.get('category')
        main_image = request.FILES.get('main_image')

        product = Product.objects.create(
            merchant=request.user.merchant_profile,
            name=name, description=description, base_price=price,
            shipping_fee=shipping_fee, category_id=category_id,
            image=main_image, is_active=False
        )

        # 2. معالجة الألوان والمقاسات (اللوجيك الجديد) 🧠
        # البيانات تأتي هكذا:
        # color_group_1 = "أحمر"
        # sizes_group_1 = ["XL", "L"]
        # qtys_group_1 = ["5", "3"]
        
        # نبحث عن كل المفاتيح التي تبدأ بـ color_group_
        for key in request.POST:
            if key.startswith('color_group_'):
                group_id = key.split('_')[-1] # الرقم (1, 2, ...)
                color_name = request.POST.get(key)
                
                # جلب المقاسات والكميات لهذا الجروب
                sizes = request.POST.getlist(f'sizes_group_{group_id}[]')
                qtys = request.POST.getlist(f'qtys_group_{group_id}[]')
                
                for i in range(len(sizes)):
                    if sizes[i] and qtys[i]:
                        ProductSize.objects.create(
                            product=product,
                            color_label=color_name,
                            size_label=sizes[i],
                            stock_quantity=qtys[i]
                        )

        # 3. الصور الإضافية
        for img in request.FILES.getlist('gallery_images'):
            ProductImage.objects.create(product=product, image=img)

        messages.success(request, "تم إضافة المنتج بنجاح ✅")
        return redirect('merchant_products')

    categories = Category.objects.all()
    return render(request, 'merchant/add_product.html', {'categories': categories})

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

        # حفظ إعدادات الشحن المجاني
        threshold = request.POST.get('free_shipping_threshold')
        is_active = request.POST.get('is_free_shipping_active') == 'on'
        
        merchant.free_shipping_threshold = int(threshold) if threshold else 0
        merchant.is_free_shipping_active = is_active
        merchant.save()
        
        messages.success(request, "تم حفظ الإعدادات.")
        # ...        
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

from datetime import timedelta

@login_required
def merchant_wallet(request):
    if not is_merchant(request.user): return redirect('home')
    
    wallet = request.user.merchant_profile.wallet
    
    # --- 1. تحرير الأرصدة المستحقة (Auto Release) ---
    time_threshold = timezone.now() - timedelta(hours=24)
    
    # نبحث عن المعاملات المعلقة القديمة
    pending_txs = WalletTransaction.objects.filter(
        wallet=wallet,
        transaction_type='PENDING', # أو النوع الذي استخدمته
        created_at__lte=time_threshold,
        is_released=False
    )
    
    released_amount = Decimal('0.00')
    if pending_txs.exists():
        with transaction.atomic():
            for tx in pending_txs:
                released_amount += tx.amount
                tx.is_released = True
                # نغير النوع لـ SALE ليدل على أنه أصبح متاحاً، أو نتركه PENDING released
                tx.transaction_type = WalletTransaction.TxType.SALE 
                tx.description += " (تم التحرير)"
                tx.save()
            
            # تحديث المحفظة
            wallet.pending_balance -= released_amount
            wallet.balance += released_amount
            wallet.save()
            
            messages.success(request, f"تم تحرير {released_amount} ج.م من الرصيد المعلق.")

    # --- 2. عرض الصفحة ---
    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
    
    return render(request, 'merchant/wallet.html', {
        'wallet': wallet,
        'transactions': transactions
    })

# (صفحة طلب السحب - سنبنيها لاحقاً)
 


from django.http import HttpResponse
from store.paymob_utils import PaymobManager
from store.models import PaymobTransaction, WalletTransaction, Wallet
from django.conf import settings

# 1. صفحة طلب الشحن (يختار المبلغ وطريقة الدفع)
from store.paymob_utils import PaymobManager
from store.models import PaymobTransaction
from django.conf import settings

@login_required
def paymob_deposit(request):
    if not is_merchant(request.user):
        return redirect('home')

    if request.method == 'POST':
        try:
            amount = float(request.POST.get('amount'))
            if amount < 10: # حد أدنى
                messages.error(request, "الحد الأدنى للشحن 10 ج.م")
                return redirect('paymob_deposit')

            amount_cents = int(amount * 100) # Paymob يتعامل بالقروش
            
            # --- 1. Paymob Setup ---
            paymob = PaymobManager()
            token = paymob.get_token()
            
            # إنشاء الطلب في Paymob
            pm_order_id = paymob.create_order(token, amount_cents)
            
            # --- 2. تسجيل المعاملة محلياً (مهم جداً للـ Callback) ---
            # نحفظ رقم الطلب (pm_order_id) لنعرف لاحقاً أن هذا شحن
            PaymobTransaction.objects.create(
                merchant=request.user.merchant_profile,
                paymob_order_id=str(pm_order_id), # تأكد أنه string
                amount_cents=amount_cents,
                is_paid=False
            )

            # --- 3. بيانات الفوترة ---
            user = request.user
            billing_data = {
                "first_name": user.first_name or "Merchant",
                "last_name": user.last_name or "User",
                "email": user.email or "merchant@bazarna.com",
                "phone_number": user.phone_primary,
                "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
                "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
            }

            # --- 4. الحصول على مفتاح الدفع ---
            payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)

            # --- 5. عرض الـ Iframe ---
            iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
            
            # نستخدم نفس قالب الـ Iframe المستخدم في الشراء
            return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})

        except Exception as e:
            print(f"Deposit Error: {e}")
            messages.error(request, "حدث خطأ أثناء الاتصال ببوابة الدفع.")
            return redirect('merchant_wallet')

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
    


from store.models import Offer
from django.utils import timezone

@login_required
def add_offer(request, product_id):
    if not is_merchant(request.user):
        return redirect('home')
    
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    try:
        current_offer = product.active_offer
    except Offer.DoesNotExist:
        current_offer = None

    is_locked = False
    if current_offer and current_offer.is_platform_offer and current_offer.is_active:
        is_locked = True # قفل التعديل
        
        # إذا حاول التاجر الالتفاف وعمل POST
        if request.method == 'POST':
            messages.error(request, "عفواً، لا يمكنك تعديل عرض تم وضعه بواسطة المنصة.")
            return redirect('merchant_products')
        
    if request.method == 'POST':
        percentage = int(request.POST.get('percentage'))
        days = int(request.POST.get('days'))
        free_shipping = request.POST.get('free_shipping') == 'on'
        threshold = int(request.POST.get('threshold', 1))
        
        Offer.objects.update_or_create(
            product=product,
            defaults={
                'discount_percentage': percentage,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=days),
                'is_active': True,
                'is_platform_offer': False,
                'free_shipping': free_shipping,
                'free_shipping_threshold': threshold
            }
        )
        messages.success(request, "تم حفظ العرض ✅")
        return redirect('merchant_products')

    # إرسال العرض الحالي للقالب
    return render(request, 'merchant/add_offer.html', {
        'product': product,
        'offer': current_offer,
          'is_locked': is_locked # المتغير الجديد
    })

@login_required
def cancel_offer(request, offer_id):
    offer = get_object_or_404(Offer, pk=offer_id, product__merchant=request.user.merchant_profile)
    
    # حماية من إلغاء عرض المنصة
    if offer.is_platform_offer:
        messages.error(request, "لا يمكنك إلغاء عرض المنصة.")
    else:
        offer.delete() # أو offer.is_active = False
        messages.success(request, "تم إلغاء العرض.")
        
    return redirect('merchant_products')


from collections import defaultdict

@login_required
def edit_product(request, product_id):
    if not is_merchant(request.user): return redirect('home')
        
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)

    if request.method == 'POST':
        # 1. تحديث البيانات الأساسية
        product.name = request.POST.get('name')
        product.base_price = request.POST.get('price')
        product.description = request.POST.get('description')
        product.save()

        # 2. تحديث المقاسات القديمة
        # (نستقبل IDs المقاسات الموجودة ونحدث كمياتها أو نحذفها)
        existing_ids = request.POST.getlist('existing_ids[]')
        
        # للحذف: أي مقاس كان موجوداً ولم يعد في القائمة المرسلة، نحذفه
        # (لكن هنا سنكتفي بتحديث الكميات المرسلة)
        for vid in existing_ids:
            qty = request.POST.get(f'qty_{vid}')
            if qty:
                size_obj = ProductSize.objects.get(id=vid)
                size_obj.stock_quantity = qty
                size_obj.save()

        # 3. إضافة الجديد (بنفس لوجيك الإضافة المتداخل)
        for key in request.POST:
            if key.startswith('new_color_group_'):
                group_id = key.split('_')[-1]
                color_name = request.POST.get(key)
                sizes = request.POST.getlist(f'new_sizes_group_{group_id}[]')
                qtys = request.POST.getlist(f'new_qtys_group_{group_id}[]')
                
                for i in range(len(sizes)):
                    if sizes[i] and qtys[i]:
                        ProductSize.objects.create(
                            product=product,
                            color_label=color_name,
                            size_label=sizes[i],
                            stock_quantity=qtys[i]
                        )

        # 4. إضافة مقاسات جديدة لألوان قديمة (Hybrid)
        # هذا يحتاج لوجيك معقد، سنكتفي بإضافة "مجموعات جديدة" بالكامل للتبسيط

        messages.success(request, "تم تحديث المنتج بنجاح ✅")
        return redirect('merchant_products')

    # --- تجهيز البيانات للعرض (Grouping) ---
    # النتيجة: { 'أحمر': [obj1, obj2], 'أزرق': [obj3] }
    variations_by_color = defaultdict(list)
    for v in product.variations.all():
        variations_by_color[v.color_label].append(v)
    
    # نحولها لقائمة عادية للقالب (Dict items لا تعمل جيداً في اللوب أحياناً)
    grouped_variations = dict(variations_by_color)

    return render(request, 'merchant/edit_product.html', {
        'product': product,
        'grouped_variations': grouped_variations # البيانات المجمعة
    })


@login_required
def delete_product(request, product_id):
    if not is_merchant(request.user):
        return redirect('home')
        
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    
    # الحل الذكي: التحقق هل المنتج مرتبط بطلبات؟
    has_orders = product.variations.filter(orderitem__isnull=False).exists()
    
    if has_orders:
        # إذا تم بيعه من قبل -> نخفيه فقط (أرشفة)
        product.is_active = False 
        product.save()
        messages.warning(request, "تم إخفاء المنتج بدلاً من حذفه (لأنه موجود في طلبات سابقة).")
    else:
        # إذا لم يُبع أبداً -> نحذفه نهائياً
        product.delete()
        messages.success(request, "تم حذف المنتج نهائياً.")
        
    return redirect('merchant_products')


@login_required
def update_order_status(request, order_id):
    # 1. التحقق من التاجر
    if not hasattr(request.user, 'merchant_profile'):
        return redirect('home')
    
    order = get_object_or_404(Order, order_id=order_id)
    
    # 2. السماح بالتعديل (بدون تعقيد مؤقتاً)
    # سنفترض أن التاجر وصل للصفحة، إذن هو يملك الصلاحية (لأننا فحصنا في order_detail)
    if order.status in [Order.Status.CART, Order.Status.WAITING_PAYMENT]:
        messages.error(request, "هذا الطلب لم يكتمل بعد.")
        return redirect('merchant_orders')
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        if new_status in ['SHIPPED', 'DELIVERED', 'CANCELLED']:
            order.status = new_status
            order.save()
            messages.success(request, "تم تغيير الحالة بنجاح.")
        
    return redirect('merchant_order_detail', order_id=order.order_id)



from store.models import WithdrawalRequest

@login_required
def request_withdrawal(request):
    if not is_merchant(request.user): return redirect('home')
    
    wallet = request.user.merchant_profile.wallet

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount'))
        phone = request.POST.get('phone')
        
        # 1. التحقق من الرصيد المتاح
        if amount > wallet.balance:
            messages.error(request, "رصيدك غير كافٍ للسحب.")
        elif amount < 1000: # حد أدنى للسحب
            messages.error(request, "الحد الأدنى للسحب 1000 ج.م")
        else:
            # 2. إنشاء الطلب
            WithdrawalRequest.objects.create(
                merchant=request.user.merchant_profile,
                amount=amount,
                phone_number=phone
            )
            # (اختياري: يمكننا خصم الرصيد فوراً وحجزه، أو الانتظار للموافقة)
            # الأفضل: خصمه فوراً لمنع سحبه مرتين
            with transaction.atomic():
                wallet.balance -= amount
                wallet.save()
                
                # نسجل العملية كـ "سحب قيد الانتظار"
                WalletTransaction.objects.create(
                    wallet=wallet, amount=-amount, 
                    transaction_type=WalletTransaction.TxType.WITHDRAWAL,
                    description="طلب سحب (قيد الانتظار)", balance_after=wallet.balance
                )

            messages.success(request, "تم تقديم طلب السحب بنجاح.")
            return redirect('merchant_wallet')

    return render(request, 'merchant/withdraw.html', {'wallet': wallet})