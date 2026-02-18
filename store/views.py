from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from collections import defaultdict
from decimal import Decimal

# الموديلات
from .models import (
    Product, Category, Order, OrderItem, ProductSize, 
    Wallet, WalletTransaction, MerchantProfile, Governorate, 
    MerchantShippingRate, SiteSetting, Favorite, Offer, 
    PaymobTransaction, Notification # تأكد أنك أنشأت Notification
)

# دوال مساعدة (إذا كانت في ملف منفصل)
from .paymob_utils import PaymobManager
from django.conf import settings


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
@login_required
def confirm_delivery_view(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action') # confirm or reject
        
        if action == 'confirm':
            order.is_confirmed_by_customer = True
            order.rating = int(request.POST.get('rating', 5))
            messages.success(request, "شكراً لتقييمك! يمكنك الآن التسوق من جديد.")
            
        elif action == 'reject':
            order.is_confirmed_by_customer = False
            order.rejection_reason = request.POST.get('reason')
            # هنا ممكن نغير حالة الطلب لـ RETURNED أو نرسل إشعار للأدمن
            order.status = Order.Status.RETURNED # أو حالة خاصة "نزاع"
            messages.warning(request, "تم تسجيل رفضك وسيتم مراجعة الإدارة.")
            
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
        is_active=True,
        merchant__wallet__balance__gte=F('merchant__minimum_balance_required') # المنتج نفسه لازم يكون مفعل
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
            offer = product.active_offer
            if offer and offer.is_active: # ...
                final_price = offer.discounted_price
        except: pass

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
                'merchant': product.merchant,
                'price_at_purchase': final_price,
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

@login_required
def cart_view(request):
    order = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    
    if order:
        print("--- Checking Cart Prices ---")
        for item in order.items.all():
            product = item.product_size.product
            current_price = product.base_price
            
            # فحص العرض
            try:
                offer = getattr(product, 'active_offer', None) # استخدام getattr للأمان
                if offer and offer.is_active:
                    from django.utils import timezone
                    if offer.end_date >= timezone.now():
                        current_price = offer.discounted_price
                        print(f"Product {product.name} has offer: {current_price}")
                    else:
                        print(f"Offer expired for {product.name}")
                else:
                    print(f"No active offer for {product.name}")
            except Exception as e:
                print(f"Error checking offer: {e}")

            # تحديث السعر
            if item.price_at_purchase != current_price:
                print(f"Updating price from {item.price_at_purchase} to {current_price}")
                item.price_at_purchase = current_price
                item.save()
        
        # إعادة حساب الإجمالي يدوياً لضمان الدقة
        # ✅ الصحيح
        total = sum(i.quantity * i.price_at_purchase for i in order.items.all())
        order.total_products_price = total
        order.save()

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
    # 1. المانع
    pending_conf = check_pending_confirmations(request.user)
    if pending_conf: return redirect('confirm_delivery_view', order_id=pending_conf.id)

    # 2. استقبال المنتجات
    selected_ids = request.GET.getlist('selected_items')
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_items')

    cart = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not cart: return redirect('home')

    if selected_ids:
        cart_items = cart.items.filter(id__in=selected_ids)
    else:
        cart_items = cart.items.all()

    if not cart_items.exists():
        messages.warning(request, "لا توجد منتجات.")
        return redirect('cart_view')

    governorates = Governorate.objects.all()

    # --- تجهيز العرض ---
    grouped_items = defaultdict(list)
    merchant_totals = defaultdict(int)
    
    for item in cart_items:
        merch = item.product_size.product.merchant
        grouped_items[merch].append(item)
        merchant_totals[merch] += item.price_at_purchase * item.quantity

    cart_structure = []
    cart_total_display = 0
    for merch, items in grouped_items.items():
        subtotal = merchant_totals[merch]
        cart_structure.append({'merchant': merch, 'items': items, 'subtotal': subtotal})
        cart_total_display += subtotal

    # ==========================================
    # معالجة الشراء (POST)
    # ==========================================
    if request.method == 'POST':
        address = request.POST.get('address')
        gov_id = request.POST.get('city')
        phone = request.POST.get('phone')
        payment_method = request.POST.get('payment_method')
        
        if not (address and gov_id and phone):
            messages.error(request, "البيانات غير مكتملة.")
            return redirect('checkout')

        gov = get_object_or_404(Governorate, pk=gov_id)
        
        created_orders = []
        grand_total_with_shipping = 0
        
        is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
        free_shipping_used = False

        try:
            with transaction.atomic():
                for group in cart_structure:
                    merchant = group['merchant']
                    items = group['items']
                    
                    # 1. حساب الشحن الأساسي
                    rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=gov).first()
                    base_shipping = rate_obj.rate if rate_obj else 50
                    
                    # 2. حساب الشحن الإضافي
                    extra_shipping = sum(i.product_size.product.shipping_fee * i.quantity for i in items)
                    
                    # 3. التحقق من عرض الشحن المجاني (Free Shipping Offer)
                    is_free_shipping_offer_applied = False
                    for item in items:
                        try:
                            offer = item.product_size.product.active_offer
                            # الشرط: العرض مفعل + فيه شحن مجاني + الكمية >= الحد الأدنى
                            if offer and offer.is_active and offer.free_shipping:
                                if item.quantity >= offer.free_shipping_threshold:
                                    is_free_shipping_offer_applied = True
                                    break # طبقنا العرض على الشحنة
                        except: pass

                    shipping_cost = base_shipping + extra_shipping

                    # تطبيق الخصم (الأولوية لعرض التاجر، ثم عرض أول طلب)
                    if is_free_shipping_offer_applied:
                        shipping_cost = 0
                        # (في هذه الحالة التاجر يتحمل الشحن، ولا نعوضه)
                    
                    elif is_first_order and not free_shipping_used:
                        shipping_cost = 0
                        free_shipping_used = True
                        # (في هذه الحالة المنصة تعوض التاجر)

                    # الحالة المبدئية
                    initial_status = Order.Status.WAITING_PAYMENT if payment_method == 'ONLINE' else Order.Status.PENDING

                    new_order = Order.objects.create(
                        customer=request.user,
                        merchant=merchant,
                        shipping_address=f"{gov.name} - {address}",
                        governorate=gov,
                        shipping_phone=phone,
                        payment_method=payment_method,
                        status=initial_status,
                        shipping_cost=shipping_cost,
                        is_first_order=(shipping_cost == 0 and not is_free_shipping_offer_applied) # لتمييز سبب المجاني
                    )
                    
                    for item in items:
                        item.order = new_order
                        item.save()
                    
                    new_order.save()
                    created_orders.append(new_order)
                    grand_total_with_shipping += new_order.final_total

                if not cart.items.exists():
                    cart.delete()

        except Exception as e:
            print(f"Error: {e}")
            messages.error(request, "حدث خطأ.")
            return redirect('checkout')

        # --- الدفع ---
        if payment_method == 'ONLINE':
            try:
                settings_obj = SiteSetting.objects.first()
                online_fees = 0
                if settings_obj:
                    fixed = float(settings_obj.platform_fee_fixed)
                    percent = float(settings_obj.platform_fee_percentage) / 100
                    online_fees = fixed + (float(grand_total_with_shipping) * percent)

                total_to_pay = float(grand_total_with_shipping) + online_fees
                amount_cents = int(total_to_pay * 100)
                
                paymob = PaymobManager()
                token = paymob.get_token()
                pm_order_id = paymob.create_order(token, amount_cents)
                
                billing_data = {
                    "first_name": request.user.first_name or "G", "last_name": request.user.last_name or "U",
                    "email": request.user.email or "no@mail.com", "phone_number": phone,
                    "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
                    "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
                }

                payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
                
                iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
                return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})

            except Exception as e:
                messages.error(request, "فشل الاتصال بالبنك.")
                return redirect('my_orders')
        
        else:
            messages.success(request, "تم استلام طلبك بنجاح!")
            return redirect('order_success')

    # --- GET ---
    settings_obj = SiteSetting.objects.first()
    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0

    return render(request, 'store/checkout.html', {
        'cart_structure': cart_structure,
        'governorates': governorates,
        'cart_total': cart_total_display,
        'selected_ids': selected_ids,
        'fee_fixed': fee_fixed,
        'fee_percent': fee_percent
    })


@login_required
def retry_payment(request, order_id):
    # جلب الطلب المعلق
    order = get_object_or_404(Order, pk=order_id, customer=request.user, status=Order.Status.WAITING_PAYMENT)
    
    try:
        from .paymob_utils import PaymobManager
        paymob = PaymobManager()
        token = paymob.get_token()
        
        # 1. حساب رسوم الدفع الإلكتروني (Online Fees)
        # (لأننا ربما لم نحسبها عند الإنشاء أو نريد تحديثها)
        settings_obj = SiteSetting.objects.first()
        online_fees = 0
        base_amount = float(order.total_products_price + order.shipping_cost)

        if settings_obj:
            fixed = float(settings_obj.platform_fee_fixed)
            percent = float(settings_obj.platform_fee_percentage) / 100
            # الرسوم = ثابت + (نسبة * المبلغ الأساسي)
            online_fees = fixed + (base_amount * percent)
        
        # 2. تحديث الطلب في الداتابيز (هام ليراه العميل والتاجر)
        order.platform_fees = online_fees
        order.final_total = base_amount + online_fees
        order.save()

        # 3. المبلغ لـ Paymob (بالقروش)
        amount_cents = int(order.final_total * 100)
        
        # إنشاء الطلب في Paymob
        pm_order_id = paymob.create_order(token, amount_cents)
        
        # بيانات العميل
        billing_data = {
            "first_name": request.user.first_name or "Guest",
            "last_name": request.user.last_name or "User",
            "email": request.user.email or "retry@payment.com",
            "phone_number": order.shipping_phone, # نستخدم هاتف الشحن المسجل
            "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
            "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
        }

        # الحصول على المفتاح
        payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
        
        # رابط الـ Iframe
        iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
        
        # عرض صفحة الدفع
        return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})

    except Exception as e:
        print(f"Retry Payment Error: {e}")
        messages.error(request, "حدث خطأ أثناء الاتصال ببوابة الدفع.")
        return redirect('my_orders')

@login_required
def customer_order_detail(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    return render(request, 'store/customer_order_detail.html', {'order': order})

# استقبال رد Paymob بعد الدفع
def payment_callback(request):
    success = request.GET.get('success')
    pm_order_id = request.GET.get('order') # رقم الطلب عند Paymob
    
    if success == "true":
        # 1. هل هذه عملية شحن رصيد؟ (نبحث في جدول PaymobTransaction)
        try:
            deposit_tx = PaymobTransaction.objects.get(paymob_order_id=pm_order_id, is_paid=False)
            
            # --- معالجة الشحن ---
            deposit_tx.is_paid = True
            deposit_tx.save()
            
            wallet = deposit_tx.merchant.wallet
            amount = Decimal(deposit_tx.amount_cents) / 100
            
            WalletTransaction.objects.create(
                wallet=wallet, amount=amount,
                transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=f"شحن رصيد (Paymob) #{deposit_tx.id}",
                balance_after=wallet.balance + amount
            )
            wallet.balance += amount
            wallet.save()
            
            messages.success(request, "تم شحن الرصيد بنجاح! 💰")
            return redirect('merchant_wallet') # توجيه للمحفظة
            
        except PaymobTransaction.DoesNotExist:
            # 2. إذن هي عملية شراء منتجات
            # (نبحث عن طلبات المستخدم المعلقة)
            # ملاحظة: هذا الافتراض خطير لو المستخدم فاتح شحن وشراء في نفس الوقت
            # الأفضل: البحث عن الطلب المرتبط بـ pm_order_id لو كنا حفظناه
            
            pending_orders = Order.objects.filter(customer=request.user, status=Order.Status.WAITING_PAYMENT)
            
            if pending_orders.exists():
                for order in pending_orders:
                    order.status = Order.Status.PENDING
                    order.save()
                
                messages.success(request, "تم دفع الطلب بنجاح! 🎉")
                return redirect('my_orders') # توجيه للطلبات
            else:
                # حالة غريبة: الدفع نجح بس مفيش طلبات ولا شحن!
                messages.warning(request, "تم الدفع، ولكن لم نجد الطلب المرتبط. يرجى التواصل مع الدعم.")
                return redirect('home')

    else:
        messages.error(request, "فشلت العملية.")
        return redirect('home')# مهم

from django.http import JsonResponse

@login_required
def calculate_shipping_api(request):
    gov_id = request.GET.get('gov_id')
    items_ids_str = request.GET.get('items', '')
    
    if not gov_id: return JsonResponse({'error': 'No ID'}, status=400)

    cart = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not cart: return JsonResponse({'shipping_details': [], 'total_shipping': 0, 'grand_total': 0})

    # فلترة العناصر المختارة
    if items_ids_str:
        try:
            items_ids = [int(i) for i in items_ids_str.split(',') if i.isdigit()]
            cart_items = cart.items.filter(id__in=items_ids)
        except:
            cart_items = cart.items.none()
    else:
        cart_items = cart.items.all()

    if not cart_items.exists():
        return JsonResponse({'shipping_details': [], 'total_shipping': 0, 'grand_total': 0})

    governorate = get_object_or_404(Governorate, pk=gov_id)
    
    # التجميع
    items_by_merchant = {}
    total_products_price = 0
    for item in cart_items:
        merch = item.product_size.product.merchant
        if merch not in items_by_merchant:
            items_by_merchant[merch] = []
        items_by_merchant[merch].append(item)
        total_products_price += item.price_at_purchase * item.quantity

    # فحص أول طلب
    is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
    free_shipping_used = False

    shipping_details = []
    total_shipping = 0

    for merchant, items in items_by_merchant.items():
        # 1. الشحن الأساسي
        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=governorate).first()
        base_shipping = rate_obj.rate if rate_obj else 50
        
        # 2. الشحن الإضافي
        extra_shipping = sum(i.product_size.product.shipping_fee * i.quantity for i in items)
        
        # 3. فحص عرض الشحن المجاني للتاجر
        is_free_shipping_offer_applied = False
        for item in items:
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_active and offer.free_shipping:
                    if item.quantity >= offer.free_shipping_threshold:
                        is_free_shipping_offer_applied = True
                        break
            except: pass

        cost = base_shipping + extra_shipping
        
        # تطبيق الخصم
        if is_free_shipping_offer_applied:
            cost = 0
        elif is_first_order and not free_shipping_used:
            cost = 0
            free_shipping_used = True
            
        total_shipping += cost
        shipping_details.append({
            'merchant_id': merchant.id,
            'cost': float(cost)
        })

    # الإجمالي النهائي
    grand_total = float(total_products_price) + float(total_shipping)

    return JsonResponse({
        'shipping_details': shipping_details,
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




def merchant_shop(request, merchant_id):
    # 1. جلب التاجر
    merchant = get_object_or_404(MerchantProfile, pk=merchant_id)
    
    # 2. جلب منتجاته المفعلة فقط
    products = Product.objects.filter(merchant=merchant, is_active=True).order_by('-created_at')
    
    # 3. حساب عدد المبيعات (اختياري كنوع من الإحصائيات للعميل)
    # sales_count = OrderItem.objects.filter(product_size__product__merchant=merchant).count()

    return render(request, 'store/merchant_shop.html', {
        'merchant': merchant,
        'products': products,
        # 'sales_count': sales_count
    })