# ==========================================
# 1. الاستدعاءات الأساسية (Imports)
# ==========================================
import json
import traceback
import uuid
from decimal import Decimal
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone as django_tz
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.conf import settings
from django.urls import reverse

# الموديلات
from accounts.models import User
from accounts.models import Country 
from .models import (
    Product, Category, Order, OrderItem, ProductSize, 
    Wallet, WalletTransaction, MerchantProfile, Governorate, 
    MerchantShippingRate, SiteSetting, Favorite, Offer, 
    PaymobTransaction, Notification, Banner, DeliveryComplaint, 
    ProductReview, PersonalVoucher, AboutUs, TermsAndCondition
)

# دوال مساعدة
from .paymob_utils import PaymobManager

# ==========================================
# إعداد دوال الإشعارات (الداخلية والموبايل - Flutter Ready)
# ==========================================
from store.utils import send_notification, notify_admins, send_push_to_user


from django.shortcuts import render

# دالة الخطأ 404
def custom_404_view(request, exception):
    return render(request, 'errors/404.html', status=404)

# دالة الخطأ 500
def custom_500_view(request):
    return render(request, 'errors/500.html', status=500)

# ==========================================
# 2. الدوال المساعدة (النظام الدولي والتأكيدات)
# ==========================================
def get_user_country(request):
    """
    🔥 دالة ذكية لتحديد دولة المستخدم الحالي (مسجل أو زائر)
    """
    if request.user.is_authenticated and request.user.country:
        return request.user.country
        
    country_id = request.session.get('user_country_id')
    if country_id:
        country = Country.objects.filter(id=country_id, is_active=True).first()
        if country:
            return country
            
    default_country = Country.objects.filter(is_active=True).first()
    if default_country:
        request.session['user_country_id'] = default_country.id
    return default_country


def set_user_country(request):
    """دالة (API) لتغيير الدولة من الواجهة للزوار"""
    if request.method == 'POST':
        country_id = request.POST.get('country_id')
        if country_id and Country.objects.filter(id=country_id, is_active=True).exists():
            request.session['user_country_id'] = int(country_id)
            if request.user.is_authenticated:
                request.user.country_id = int(country_id)
                request.user.save()
            messages.success(request, "تم تغيير دولة المتجر بنجاح.")
    return redirect(request.META.get('HTTP_REFERER', 'home'))


def check_pending_confirmations(user):
    """فحص الطلبات المعلقة التي تحتاج تأكيد استلام أو رفض"""
    if not user.is_authenticated: 
        return None
    pending = Order.objects.filter(
        customer=user, 
        status__in=[Order.Status.DELIVERED, Order.Status.RETURNED], 
        is_confirmed_by_customer__isnull=True
    ).first()
    return pending


# ==========================================
# 3. دوال المتجر الأساسية (Store Views)
# ==========================================
def home(request):
    if request.user.is_authenticated and request.user.is_banned:
        return render(request, 'account/banned.html')
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
        
    pending_conf = check_pending_confirmations(request.user)
    if pending_conf:
        return redirect('confirm_delivery_view', order_id=pending_conf.id)
        
    if request.user.is_authenticated and not request.user.phone_primary:
        return redirect('complete_profile')

    current_country = get_user_country(request)

    active_banners = Banner.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    )
    
    today = django_tz.now().date()
    query = request.GET.get('q')
    category_id = request.GET.get('category')
    
    settings_obj = SiteSetting.objects.first()
    
    products = Product.objects.filter(
        merchant__user__country=current_country, 
        is_active=True,
        is_approved=True,
        merchant__user__is_active=True,
        merchant__user__is_banned=False
    ).filter(
        Q(merchant__subscription_end_date__isnull=True) | Q(merchant__subscription_end_date__gte=today)
    )
    
    products = products.filter(merchant__wallet__balance__gte=F('merchant__minimum_balance_required'))

    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category_id:
        products = products.filter(category_id=category_id)
        
    products = products.order_by('-created_at')

    offers = Product.objects.filter(
        merchant__user__country=current_country, 
        active_offer__is_active=True,
        active_offer__end_date__gte=django_tz.now(), 
        is_active=True,
        is_approved=True,
        merchant__user__is_active=True,
        merchant__user__is_banned=False
    ).filter(
        Q(merchant__subscription_end_date__isnull=True) | Q(merchant__subscription_end_date__gte=today)
    ).order_by('-active_offer__discount_percentage')[:5]
    
    categories = Category.objects.all()
    
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    return render(request, 'store/home.html', {
        'current_country': current_country,
        'products': products,
        'categories': categories,
        'selected_category': int(category_id) if category_id else None,
        'search_query': query,
        'offers': offers,
        'unread_notifications_count': unread_count,
        'banners': active_banners,
    })


def product_detail(request, pk):
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
        
    product = get_object_or_404(Product, pk=pk)
    current_country = get_user_country(request)
    
    if product.merchant.user.country != current_country:
        messages.error(request, "هذا المنتج غير متوفر في دولتك الحالية.")
        return redirect('home')

    variations = product.variations.filter(stock_quantity__gt=0)
    today = django_tz.now().date()
    available_colors = set(v.color_label for v in variations)
    variants_data = {}
    for v in variations:
        if v.color_label not in variants_data:
            variants_data[v.color_label] = []
        variants_data[v.color_label].append({
            'id': v.id, 'size': v.size_label, 'qty': v.stock_quantity
        })

    variants_json = json.dumps(variants_data)

    similar_products = Product.objects.filter(
        merchant__user__country=current_country,
        category=product.category,
        is_active=True,
        is_approved=True
    ).exclude(id=product.id)[:5]
    
    is_fav = False
    has_purchased = False
    
    if request.user.is_authenticated:
        is_fav = Favorite.objects.filter(user=request.user, product=product).exists()
        has_purchased = Order.objects.filter(
            customer=request.user,
            status='DELIVERED', 
            items__product_size__product=product 
        ).exists()

    return render(request, 'store/product_detail.html', {
        'product': product,
        'available_colors': available_colors,
        'variants_json': variants_json, 
        'similar_products': similar_products,
        'has_purchased': has_purchased,
        'is_fav': is_fav
    })


def categories_page(request):
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
    categories = Category.objects.all()
    return render(request, 'store/categories.html', {'categories': categories})


def merchant_shop(request, merchant_id):
    merchant = get_object_or_404(MerchantProfile, pk=merchant_id)
    current_country = get_user_country(request)
    
    if merchant.user.country != current_country:
        messages.error(request, "هذا المتجر غير متاح في دولتك الحالية.")
        return redirect('home')
        
    products = Product.objects.filter(merchant=merchant, is_active=True).order_by('-created_at')
    return render(request, 'store/merchant_shop.html', {
        'merchant': merchant, 'products': products,
    })


# ==========================================
# 4. السلة وإتمام الطلب (Cart & Checkout)
# ==========================================
@login_required
def add_to_cart(request, pk):
    if request.method == 'POST':
        size_id = request.POST.get('size_id')
        quantity = request.POST.get('quantity', 1)
        
        if not size_id:
            messages.error(request, "الرجاء اختيار المقاس واللون.")
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        product_size = get_object_or_404(ProductSize, pk=size_id)
        product = product_size.product 
        
        current_country = get_user_country(request)
        if product.merchant.user.country != current_country:
            messages.error(request, "لا يمكنك إضافة منتجات من دولة أخرى لسلتك الحالية.")
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        quantity = int(quantity)
        if quantity > product_size.stock_quantity:
            messages.error(request, f"عفواً، الكمية المتاحة حالياً هي {product_size.stock_quantity} فقط.")
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        final_price = product.base_price
        try:
            offer = product.active_offer
            if offer and offer.is_active: 
                final_price = offer.discounted_price
        except: pass

        order, created = Order.objects.get_or_create(
            customer=request.user, status=Order.Status.CART, 
            defaults={'total_products_price': 0, 'final_total': 0, 'shipping_address': 'مؤقت', 'shipping_phone': request.user.phone_primary}
        )

        try:
            order_item, item_created = OrderItem.objects.get_or_create(
                order=order, product_size=product_size,
                defaults={'quantity': quantity, 'price_at_purchase': final_price, 'merchant': product.merchant}
            )

            if not item_created:
                order_item.quantity += quantity
                order_item.price_at_purchase = final_price 
                order_item.save() 
            
            order.save()
            messages.success(request, "تمت الإضافة للسلة بنجاح! 🛍️")
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        except ValidationError as e:
            error_message = ' '.join(e.messages) if hasattr(e, 'messages') else str(e)
            error_message = error_message.replace("['", "").replace("']", "")
            messages.error(request, error_message)
            return redirect(request.META.get('HTTP_REFERER', 'home'))

    return redirect('home')


@login_required
def cart_view(request):
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
    
    order = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    personal_vouchers = PersonalVoucher.objects.filter(customer=request.user, is_used=False, expires_at__gt=django_tz.now())
    
    if order:
        current_country = get_user_country(request)
        invalid_items = order.items.exclude(merchant__user__country=current_country)
        if invalid_items.exists():
            invalid_items.delete()
            messages.warning(request, "تم إزالة بعض المنتجات من السلة لأنها غير متاحة في دولتك الحالية.")

        for item in order.items.all():
            product = item.product_size.product
            current_price = product.base_price
            try:
                offer = getattr(product, 'active_offer', None)
                if offer and offer.is_active and offer.end_date >= timezone.now():
                    current_price = offer.discounted_price
            except Exception: pass

            if item.price_at_purchase != current_price:
                item.price_at_purchase = current_price
                item.save()
        
        total = sum(i.quantity * i.price_at_purchase for i in order.items.all())
        order.total_products_price = total
        order.save()

    return render(request, 'store/cart.html', {'order': order, 'personal_vouchers': personal_vouchers})


@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__customer=request.user, order__status=Order.Status.CART)
    item.delete()
    return redirect('cart_view')


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


@login_required
def checkout(request):
    pending_conf = check_pending_confirmations(request.user)
    if pending_conf: return redirect('confirm_delivery_view', order_id=pending_conf.id)

    selected_ids = request.GET.getlist('selected_items')
    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_items')

    cart = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not cart or not cart.items.exists():
        return redirect('home')

    if selected_ids:
        valid_ids = [int(i) for i in selected_ids if str(i).isdigit()]
        cart_items = cart.items.filter(id__in=valid_ids)
    else:
        cart_items = cart.items.all()

    if not cart_items.exists():
        messages.warning(request, "لم تختر منتجات.")
        return redirect('cart_view')

    current_country = get_user_country(request)
    governorates = Governorate.objects.filter(country=current_country)

    grouped_items = defaultdict(list)
    merchant_totals = defaultdict(int)
    
    settings_obj = SiteSetting.objects.first()
    limit_pct = settings_obj.referral_discount_limit_pct if settings_obj else 10
    total_max_discount = 0 
    
    for item in cart_items:
        merch = item.product_size.product.merchant
        grouped_items[merch].append(item)
        price = item.price_at_purchase
        qty = item.quantity
        merchant_totals[merch] += price * qty
        total_max_discount += (price * Decimal(limit_pct) / 100) * qty

    user_balance = request.user.referral_balance
    applicable_discount = min(user_balance, total_max_discount)

    cart_structure = []
    cart_total_display = 0
    for merch, items in grouped_items.items():
        subtotal = merchant_totals[merch]
        cart_structure.append({'merchant': merch, 'items': items, 'subtotal': subtotal})
        cart_total_display += subtotal

    if request.method == 'POST':
        address = request.POST.get('address')
        gov_id = request.POST.get('city')
        phone = request.POST.get('phone')
        payment_method = request.POST.get('payment_method')
        use_wallet = request.POST.get('use_wallet') == 'on'
        wallet_number = request.POST.get('wallet_number')
        
        voucher_code = request.POST.get('admin_voucher_code')
        applied_voucher = None
        if voucher_code:
            applied_voucher = PersonalVoucher.objects.filter(
                code=voucher_code, customer=request.user, is_used=False, expires_at__gt=django_tz.now()
            ).first()

        if not (address and gov_id and phone):
            messages.error(request, "البيانات ناقصة.")
            return redirect('checkout')

        gov = get_object_or_404(Governorate, pk=gov_id, country=current_country)
        created_orders = []
        grand_total_final = 0
        
        remaining_discount = applicable_discount if use_wallet else Decimal(0)
        total_discount_used = Decimal(0)
        is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
        free_shipping_used = False
        recipient_name = request.POST.get('recipient_name', '').strip()
        if not recipient_name:
            recipient_name = f"{request.user.first_name} {request.user.last_name}"

        if applied_voucher:
            voucher_discount_pct = Decimal(applied_voucher.discount_percentage) / Decimal(100)
            voucher_max_discount = Decimal(applied_voucher.max_discount_amount)
            voucher_items_left = applied_voucher.remaining_items
            voucher_discount_accumulated = Decimal(0)

        try:
            with transaction.atomic():
                for group in cart_structure:
                    merchant = group['merchant']
                    items = group['items']
                    
                    rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=gov).first()
                    base_shipping = rate_obj.rate if rate_obj else Decimal(50)
                    extra_shipping = sum(i.product_size.product.shipping_fee * i.quantity for i in items)
                    
                    is_free_offer = False
                    for item in items:
                        try:
                            off = item.product_size.product.active_offer
                            if off and off.is_active and off.free_shipping and item.quantity >= off.free_shipping_threshold:
                                is_free_offer = True
                                break
                        except: pass

                    shipping_cost = base_shipping + extra_shipping
                    if is_free_offer or (applied_voucher and applied_voucher.free_shipping):
                        shipping_cost = 0
                    elif is_first_order and not free_shipping_used:
                        shipping_cost = 0
                        free_shipping_used = True

                    initial_status = Order.Status.WAITING_PAYMENT if payment_method in ['ONLINE', 'WALLET'] else Order.Status.PENDING
                    admin_discount_val = Decimal(0)

                    if applied_voucher and voucher_items_left > 0 and voucher_discount_pct > 0:
                        for item in items:
                            if voucher_items_left <= 0 or voucher_discount_accumulated >= voucher_max_discount:
                                break
                            qty_to_discount = min(item.quantity, voucher_items_left)
                            item_price = Decimal(item.price_at_purchase)
                            potential_discount = (item_price * voucher_discount_pct) * Decimal(qty_to_discount)
                            actual_discount = min(potential_discount, voucher_max_discount - voucher_discount_accumulated)
                            
                            admin_discount_val += actual_discount
                            voucher_discount_accumulated += actual_discount
                            voucher_items_left -= qty_to_discount 

                    new_order = Order.objects.create(
                        customer=request.user, merchant=merchant, recipient_name=recipient_name,
                        shipping_address=f"{gov.name} - {address}", governorate=gov, shipping_phone=phone,
                        payment_method=payment_method, status=initial_status, shipping_cost=shipping_cost,
                        is_first_order=(shipping_cost == 0 and not is_free_offer and not (applied_voucher and applied_voucher.free_shipping)),
                        admin_discount=admin_discount_val
                    )
                    
                    for item in items:
                        item.order = new_order
                        if remaining_discount > 0:
                            item_limit = (Decimal(item.price_at_purchase) * Decimal(limit_pct) / 100) * item.quantity
                            discount_to_apply = min(remaining_discount, item_limit)
                            item.referral_discount = discount_to_apply
                            remaining_discount -= discount_to_apply
                            total_discount_used += discount_to_apply
                        else:
                            item.referral_discount = 0
                        item.save()
                    
                    new_order.save()
                    created_orders.append(new_order)
                    grand_total_final += new_order.final_total

                    # 🔥 الإشعارات 
                    if payment_method == 'COD':
                        try:
                            # إشعار داخل النظام
                            send_notification(
                                user=merchant.user, title="طلب جديد! 🛍️",
                                message=f"وصلك طلب جديد #{new_order.order_id} من {new_order.recipient_name}.",
                                link=f"/merchant/order/{new_order.order_id}/"
                            )
                            # Push Notification
                            send_push_to_user(
                                user=merchant.user, title="طلب جديد! 🛍️",
                                body=f"وصلك طلب جديد #{new_order.order_id} من {new_order.recipient_name}."
                            )
                        except: pass

                if total_discount_used > 0:
                    request.user.referral_balance -= total_discount_used
                    request.user.save()

                if applied_voucher and created_orders:
                    applied_voucher.remaining_items = voucher_items_left
                    if voucher_items_left == 0:
                        applied_voucher.is_used = True 
                    applied_voucher.save()

                if not cart.items.exists():
                    cart.delete()

        except Exception as e:
            print(f"Checkout Error: {traceback.format_exc()}") 
            messages.error(request, f"حدث خطأ أثناء إتمام الطلب: {str(e)}")
            return redirect('checkout')

        # معالجة Paymob
        if payment_method in ['ONLINE', 'WALLET']:
            try:
                online_fees = 0
                if settings_obj:
                    fixed = float(settings_obj.platform_fee_fixed)
                    percent = float(settings_obj.platform_fee_percentage) / 100
                    online_fees = fixed + (float(grand_total_final) * percent)

                total_to_pay = float(grand_total_final) + online_fees
                
                if created_orders:
                    first_order = created_orders[0]
                    first_order.platform_fees = online_fees
                    first_order.final_total += Decimal(online_fees)
                    first_order.save()

                paymob = PaymobManager()
                token = paymob.get_token()
                amount_cents = int(total_to_pay * 100)
                pm_order_id = paymob.create_order(token, amount_cents)
                
                for o in created_orders:
                    o.paymob_order_id = pm_order_id
                    o.save()
                
                name_parts = recipient_name.split(' ', 1)
                billing_data = {
                    "first_name": name_parts[0] if name_parts else (request.user.first_name or "G"), 
                    "last_name": name_parts[1] if len(name_parts) > 1 else (request.user.last_name or "U"),
                    "email": request.user.email or "no@mail.com", "phone_number": phone,
                    "city": gov.name, "country": current_country.code if current_country else "EG", "state": "NA", "street": "NA", "building": "NA", "floor": "NA", "apartment": "NA", "postal_code": "NA", "shipping_method": "NA"
                }

                if payment_method == 'ONLINE':
                    payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
                    iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
                    return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})
                
                elif payment_method == 'WALLET':
                    if not wallet_number:
                        messages.error(request, "رقم المحفظة مطلوب.")
                        return redirect('my_orders')
                    billing_data['phone_number'] = wallet_number 
                    redirect_url = paymob.pay_with_wallet(token, amount_cents, pm_order_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
                    return redirect(redirect_url)

            except Exception as e:
                print(f"Paymob Error: {e}")
                messages.error(request, "فشل الاتصال بالبنك. تم حفظ الطلب، يرجى المحاولة من 'طلباتي'.")
                return redirect('my_orders')
        
        else:
            # 🔥 إشعار العميل بنجاح الطلب كاش
            try:
                send_notification(
                    user=request.user, title="تم استلام طلبك! 🎉",
                    message="تم استلام طلبك بنجاح وسيقوم التاجر بتأكيده قريباً.",
                    link="/my-orders/"
                )
                send_push_to_user(
                    user=request.user, title="تم استلام طلبك! 🎉",
                    body="تم استلام طلبك بنجاح وسيقوم التاجر بالبدء في تجهيزه."
                )
            except: pass
            messages.success(request, "تم استلام طلبك بنجاح!")
            return redirect('order_success')

    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0

    personal_vouchers = PersonalVoucher.objects.filter(
        customer=request.user, is_used=False, expires_at__gt=django_tz.now() 
    )

    return render(request, 'store/checkout.html', {
        'cart_structure': cart_structure, 'governorates': governorates,
        'cart_total': cart_total_display, 'selected_ids': selected_ids,
        'fee_fixed': fee_fixed, 'fee_percent': fee_percent,
        'applicable_discount': applicable_discount, 'personal_vouchers': personal_vouchers,
        'current_country': current_country
    })


@login_required
def retry_payment(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user, status=Order.Status.WAITING_PAYMENT)
    
    old_fees = order.platform_fees if order.platform_fees else Decimal(0)
    base_total = order.final_total - old_fees
    settings_obj = SiteSetting.objects.first()
    
    if request.method == 'POST':
        method = request.POST.get('payment_method')
        wallet_number = request.POST.get('wallet_number')
        
        try:
            if method == 'COD':
                order.payment_method = 'COD'
                order.status = Order.Status.PENDING 
                order.platform_fees = 0 
                order.final_total = base_total 
                order.save()
                
                # 🔥 إشعارات تحويل الدفع لكاش
                try:
                    # للعميل
                    send_notification(
                        user=order.customer, title="تغيير طريقة الدفع! 🔄",
                        message=f"تم تغيير طريقة الدفع للطلب #{order.order_id} إلى الدفع عند الاستلام.",
                        link="/my-orders/"
                    )
                    send_push_to_user(order.customer, "طريقة الدفع تغيرت 🔄", "تم تحويل طلبك ليدفع عند الاستلام كاش.")
                    
                    # للتاجر
                    send_notification(
                        user=order.merchant.user, title="طلب جديد (تم تحويله لكاش)! 🛍️",
                        message=f"قام العميل بتغيير طريقة الدفع للطلب #{order.order_id} إلى كاش وهو بانتظار تجهيزك.",
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, "طلب جديد! 🛍️", f"تم تحويل الطلب #{order.order_id} لكاش وهو بانتظار تجهيزك.")
                except: pass
                
                messages.success(request, "تم تحويل الطلب إلى الدفع عند الاستلام بنجاح.")
                return redirect('customer_order_detail', order_id=order.id) 
            
            elif method in ['ONLINE', 'WALLET']:
                paymob = PaymobManager()
                token = paymob.get_token()
                
                online_fees = 0
                if settings_obj:
                    fixed = float(settings_obj.platform_fee_fixed)
                    percent = float(settings_obj.platform_fee_percentage) / 100
                    online_fees = fixed + (float(base_total) * percent)
                
                order.platform_fees = online_fees
                order.final_total = Decimal(base_total) + Decimal(online_fees)
                order.payment_method = method
                order.save()

                amount_cents = int(order.final_total * 100)
                pm_order_id = paymob.create_order(token, amount_cents)

                cache.set(f'paymob_orders_{pm_order_id}', [order.id], 3600)
                
                billing_data = {
                    "first_name": request.user.first_name or "G", "last_name": request.user.last_name or "U",
                    "email": request.user.email or "retry@pay.com", "phone_number": order.shipping_phone,
                    "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
                    "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
                }

                if method == 'ONLINE':
                    payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
                    iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
                    return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})
                
                elif method == 'WALLET':
                    if not wallet_number:
                        messages.error(request, "رقم المحفظة مطلوب.")
                        return redirect('retry_payment', order_id=order.id)
                    billing_data['phone_number'] = wallet_number
                    redirect_url = paymob.pay_with_wallet(token, amount_cents, pm_order_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
                    return redirect(redirect_url)

        except Exception as e:
            messages.error(request, "حدث خطأ أثناء الاتصال بالبنك، يرجى المحاولة مرة أخرى.")
            return redirect('retry_payment', order_id=order.id)

    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0
    
    return render(request, 'store/retry_payment.html', {
        'order': order, 'base_total': base_total,
        'fee_fixed': fee_fixed, 'fee_percent': fee_percent
    })


# ==========================================
# 5. دوال لوحة التحكم للمستخدم والمتابعة
# ==========================================
@login_required
def confirm_delivery_view(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        
        if order.status == Order.Status.DELIVERED:
            if action == 'confirm':
                order.is_confirmed_by_customer = True
                try: rating_val = int(request.POST.get('rating', 5))
                except ValueError: rating_val = 5
                    
                review_comment = request.POST.get('review_comment', '').strip()
                final_comment = review_comment if review_comment else f"تقييم مجمع من الطلب #{order.order_id or order.id}"
                
                order.rating = rating_val
                order.save()
                
                for item in order.items.all():
                    product = item.product_size.product
                    ProductReview.objects.update_or_create(
                        product=product, user=request.user, 
                        defaults={'rating': rating_val, 'comment': final_comment}
                    )
                    if hasattr(product, 'update_average_rating'): product.update_average_rating()

                # 🔥 إشعار تأكيد الاستلام وتقييم
                try:
                    send_notification(
                        user=order.merchant.user, title="تأكيد استلام وتقييم! ⭐️",
                        message=f"أكد العميل استلام الطلب #{order.order_id} وقيمه بـ {rating_val} نجوم.",
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, "استلام وتقييم ⭐️", f"العميل استلم الطلب #{order.order_id} واداك {rating_val} نجوم!")
                except: pass
                
                messages.success(request, "شكراً لك! تم تأكيد استلامك وتقييم المنتجات بنجاح.")
                return redirect('home')
                
            elif action == 'reject':
                whatsapp_number = request.POST.get('whatsapp_number', '').strip()
                reason = request.POST.get('reason', 'التاجر يدعي التسليم، ولكنني لم أستلم الطلب أو قمت بإرجاعه للمندوب!')
                
                if not whatsapp_number or len(whatsapp_number) < 11:
                    messages.error(request, "يجب إدخال رقم واتساب صحيح لا يقل عن 11 رقماً.")
                    return redirect(request.META.get('HTTP_REFERER', 'home'))
                
                order.is_confirmed_by_customer = False
                order.rejection_reason = reason
                order.status = Order.Status.RETURNED 
                order.save()
                
                DeliveryComplaint.objects.update_or_create(
                    order=order, defaults={
                        'customer': request.user, 'complaint_text': reason,
                        'whatsapp_number': whatsapp_number, 'is_resolved': False,
                    }
                )
                
                # 🔥 إشعار الشكوى للتاجر
                try:
                    send_notification(
                        user=order.merchant.user, title="شكوى بعدم الاستلام! ⚠️",
                        message=f"فتح العميل شكوى لعدم استلام الطلب #{order.order_id}. تم إيقاف أرباح الطلب للمراجعة.",
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, "تحذير: شكوى عدم استلام ⚠️", f"العميل فتح شكوى بعدم استلام الطلب #{order.order_id}.")
                except: pass

                notify_admins(
                    title="شكوى عدم استلام 🚨", 
                    message=f"العميل {request.user.first_name} فتح شكوى بخصوص الطلب #{order.order_id} متهماً التاجر بادعاء التسليم.",
                    link=reverse('admin_complaints_list')
                )

                messages.warning(request, "تم تسجيل شكواك بعدم الاستلام! أوقفنا أرباح الطلب وسنحقق فوراً.")
                return redirect('my_orders')

        elif order.status == Order.Status.RETURNED:
            if action == 'confirm':
                order.is_confirmed_by_customer = True
                order.save()
                
                DeliveryComplaint.objects.update_or_create(
                    order=order, defaults={
                        'customer': request.user, 
                        'complaint_text': "مرتجع متفق عليه: العميل والتاجر أكدوا المرتجع. بانتظار تدخل الإدارة لتسوية الأموال (الريفاند/الشحن).",
                        'whatsapp_number': request.user.phone_primary or "غير محدد", 
                        'is_resolved': False,
                    }
                )
                
                # 🔥 إشعار التاجر بتأكيد المرتجع
                try:
                    send_notification(
                        user=order.merchant.user, title="تأكيد المرتجع من العميل 🔄",
                        message=f"أكد العميل إرجاع الطلب #{order.order_id}. الطلب الآن لدى الإدارة لتسوية الحسابات.",
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, "العميل أكد المرتجع 🔄", f"تم تأكيد إرجاع الطلب #{order.order_id} وجاري التسوية.")
                except: pass

                notify_admins(
                    title="مرتجع بانتظار التسوية 🔄", 
                    message=f"تم تأكيد إرجاع الطلب #{order.order_id} من الطرفين. يرجى الدخول لتسوية الحسابات المالية.",
                    link=reverse('admin_complaints_list')
                )

                messages.success(request, "تم تأكيد عملية الإرجاع. الإدارة ستقوم بتسوية أموالك في أقرب وقت.")
                return redirect('home')
                
            elif action == 'reject':
                whatsapp_number = request.POST.get('whatsapp_number', '').strip()
                reason = "المندوب يدعي أن الطلب مرتجع، لكنني استلمته ودفعت ثمنه كاملاً!"
                
                if not whatsapp_number or len(whatsapp_number) < 11:
                    messages.error(request, "يجب إدخال رقم واتساب صحيح.")
                    return redirect(request.META.get('HTTP_REFERER', 'home'))
                
                order.is_confirmed_by_customer = False
                order.rejection_reason = reason
                order.save()
                
                DeliveryComplaint.objects.update_or_create(
                    order=order, defaults={
                        'customer': request.user, 'complaint_text': reason,
                        'whatsapp_number': whatsapp_number, 'is_resolved': False,
                    }
                )
                
                # 🔥 إشعار شكوى التلاعب للتاجر
                try:
                    send_notification(
                        user=order.merchant.user, title="شكوى خطيرة! 🚨",
                        message=f"العميل يشتكي بأنه استلم الطلب #{order.order_id} ودفع ثمنه، رغم تسجيله كمرتجع.",
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, "شكوى تلاعب! 🚨", f"العميل يدعي استلامه ودفع ثمن الطلب #{order.order_id} رغم تسجيله كمرتجع.")
                except: pass

                notify_admins(
                    title="شكوى تلاعب خطيرة 🚨", 
                    message=f"العميل يدعي أنه استلم ودفع ثمن الطلب #{order.order_id} رغم أن التاجر أو المندوب سجله كمرتجع!",
                    link=reverse('admin_complaints_list')
                )

                messages.warning(request, "تم تسجيل الشكوى الخطيرة! سنتواصل معك فوراً.")
                return redirect('my_orders')

    return render(request, 'store/confirm_delivery.html', {'order': order})


@login_required
def customer_order_detail(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    expected_fees = order.platform_fees
    if order.status == Order.Status.WAITING_PAYMENT and expected_fees == 0:
        settings_obj = SiteSetting.objects.first()
        if settings_obj:
            base = float(order.total_products_price + order.shipping_cost)
            fixed = float(settings_obj.platform_fee_fixed)
            percent = float(settings_obj.platform_fee_percentage) / 100
            expected_fees = fixed + (base * percent)

    return render(request, 'store/customer_order_detail.html', {
        'order': order, 'expected_fees': round(expected_fees, 2) 
    })


def order_success(request):
    return render(request, 'store/order_success.html')


@login_required
def my_orders(request):
    orders = Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).order_by('-created_at')
    return render(request, 'store/my_orders.html', {'orders': orders})


# ==========================================
# 6. الملحقات والميزات (API, Callbacks, Reviews)
# ==========================================
def payment_callback(request):
    """الاستقبال الآلي لرد Paymob بعد عمليات الدفع"""
    success = request.GET.get('success')
    pm_order_id = request.GET.get('order') 
    transaction_id = request.GET.get('id') 
    
    if success == "true" or success == True:
        # 1. فحص الشحن للمحفظة
        try:
            deposit_tx = PaymobTransaction.objects.get(paymob_order_id=pm_order_id, is_paid=False)
            deposit_tx.is_paid = True
            deposit_tx.save()
            
            wallet = deposit_tx.merchant.wallet
            total_paid = Decimal(deposit_tx.amount_cents) / 100 
            
            settings_obj = SiteSetting.objects.first()
            fixed_fee = Decimal(settings_obj.platform_fee_fixed) if settings_obj else Decimal('0.00')
            percent_fee = Decimal(settings_obj.platform_fee_percentage) / Decimal('100.00') if settings_obj else Decimal('0.00')
            
            net_amount = round((total_paid - fixed_fee) / (Decimal('1.00') + percent_fee), 2)
            if net_amount < Decimal('0.00'):
                net_amount = Decimal('0.00')
                
            fees_deducted = total_paid - net_amount 
            
            WalletTransaction.objects.create(
                wallet=wallet, amount=net_amount,
                transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=f"شحن رصيد إلكتروني #{deposit_tx.id} (خصم {fees_deducted} ج.م رسوم دفع)",
                balance_after=wallet.balance + net_amount
            )
            wallet.balance += net_amount
            wallet.save()
            
            # 🔥 إشعارات شحن المحفظة
            try:
                send_notification(
                    user=deposit_tx.merchant.user, title="تم شحن رصيدك بنجاح! 💰",
                    message=f"تم شحن محفظتك بمبلغ {net_amount} ج.م (الصافي بعد رسوم الدفع).", link="/merchant/wallet/"
                )
                send_push_to_user(deposit_tx.merchant.user, "شحن المحفظة 💳", f"تم إضافة مبلغ {net_amount} ج.م لمحفظتك.")
            except: pass
            
            messages.success(request, f"تم شحن الرصيد بنجاح! 💰 (صافي: {net_amount} ج.م)")
            return redirect('merchant_wallet')
            
        except PaymobTransaction.DoesNotExist:
            # 2. فحص الدفع للطلبات
            pending_orders = Order.objects.filter(paymob_order_id=pm_order_id, status=Order.Status.WAITING_PAYMENT)
            if pending_orders.exists():
                with transaction.atomic():
                    for order in pending_orders:
                        order.status = Order.Status.PENDING
                        order.paymob_transaction_id = transaction_id
                        order.save()
                        
                        # 🔥 إشعار التاجر بدفع الطلب
                        try:
                            send_notification(
                                user=order.merchant.user, title="طلب مدفوع جديد! 💳",
                                message=f"تم دفع الطلب #{order.order_id} إلكترونياً وهو بانتظار تأكيدك.", link=f"/merchant/order/{order.order_id}/"
                            )
                            send_push_to_user(order.merchant.user, "طلب جديد مدفوع! 💳", f"العميل دفع ثمن الطلب #{order.order_id} أونلاين وبانتظار التجهيز.")
                        except: pass
                            
                # 🔥 إشعار العميل بنجاح الدفع
                try:
                    send_notification(
                        user=request.user, title="تم الدفع بنجاح! 🎉",
                        message="تم تأكيد الدفع لطلبك وسيقوم التاجر بتجهيزه قريباً.", link="/my-orders/"
                    )
                    send_push_to_user(request.user, "الدفع تم بنجاح! 🎉", "استلمنا مدفوعاتك والتاجر بيبدأ يجهز طلبك.")
                except: pass
                
                messages.success(request, "تم دفع الطلب بنجاح! 🎉")
                return redirect('my_orders')
            else:
                messages.warning(request, "تم الدفع، ولكن لم نتمكن من تحديد الطلب. يرجى التواصل مع الدعم.")
                return redirect('home')
    else:
        messages.error(request, "فشلت عملية الدفع أو تم إلغاؤها.")
        return redirect('my_orders')


@login_required
def calculate_shipping_api(request):
    """إرجاع بيانات الشحن كـ JSON"""
    gov_id = request.GET.get('gov_id')
    items_ids_str = request.GET.get('items', '')
    
    if not gov_id: return JsonResponse({'error': 'No ID'}, status=400)

    cart = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    if not cart: return JsonResponse({'shipping_details': [], 'total_shipping': 0, 'grand_total': 0})

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

    current_country = get_user_country(request)
    governorate = get_object_or_404(Governorate, pk=gov_id, country=current_country)
    
    items_by_merchant = {}
    total_products_price = 0
    for item in cart_items:
        merch = item.product_size.product.merchant
        if merch not in items_by_merchant:
            items_by_merchant[merch] = []
        items_by_merchant[merch].append(item)
        total_products_price += item.price_at_purchase * item.quantity

    is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
    free_shipping_used = False
    shipping_details = []
    total_shipping = 0

    for merchant, items in items_by_merchant.items():
        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=governorate).first()
        base_shipping = rate_obj.rate if rate_obj else 50
        extra_shipping = sum(i.product_size.product.shipping_fee * i.quantity for i in items)
        
        is_free_shipping_offer_applied = False
        for item in items:
            try:
                offer = item.product_size.product.active_offer
                if offer and offer.is_active and offer.free_shipping and item.quantity >= offer.free_shipping_threshold:
                    is_free_shipping_offer_applied = True
                    break
            except: pass

        cost = base_shipping + extra_shipping
        
        if is_free_shipping_offer_applied: cost = 0
        elif is_first_order and not free_shipping_used:
            cost = 0
            free_shipping_used = True
            
        total_shipping += cost
        shipping_details.append({'merchant_id': merchant.id, 'cost': float(cost)})

    grand_total = float(total_products_price) + float(total_shipping)
    return JsonResponse({
        'shipping_details': shipping_details,
        'total_shipping': float(total_shipping),
        'grand_total': grand_total
    })


@login_required
def toggle_favorite(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
    
    if not created:
        favorite.delete()
        added = False
    else:
        added = True
    
    return JsonResponse({'added': added, 'count': request.user.favorites.count()})


@login_required
def wishlist_view(request):
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
        
    current_country = get_user_country(request)
    favorites = Favorite.objects.filter(
        user=request.user, 
        product__merchant__user__country=current_country
    ).select_related('product')
    
    return render(request, 'store/wishlist.html', {'favorites': favorites})


@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'store/notifications.html', {'notifications': notifications})


@login_required
def referral_center(request):
    user = request.user
    settings_obj = SiteSetting.objects.first()
    grace_hours = settings_obj.referral_grace_period_hours if settings_obj else 24
    
    is_eligible = False
    time_diff = timezone.now() - user.date_joined
    if time_diff.total_seconds() / 3600 < grace_hours and not user.invited_by:
        is_eligible = True

    if request.method == 'POST':
        code = request.POST.get('code')
        try:
            inviter = User.objects.get(referral_code=code)
            if inviter == user:
                messages.error(request, "لا يمكنك دعوة نفسك!")
            elif user.invited_by:
                messages.error(request, "لقد استخدمت كود دعوة مسبقاً.")
            else:
                user.invited_by = inviter
                user.save()
                
                # 🔥 إشعار الدعوة
                try:
                    send_notification(
                        user=inviter, title="دعوة ناجحة! 🎉",
                        message=f"قام {user.first_name} باستخدام كود دعوتك. ستحصل على المكافأة عند أول شراء له.", link="/referral-center/"
                    )
                    send_push_to_user(inviter, "مبروك دعوة ناجحة! 🎉", f"{user.first_name} سجل بكودك، هينزلك مكافأة أول ما يشتري.")
                except: pass
                
                messages.success(request, "تم تفعيل كود الدعوة بنجاح! 🎉")
                return redirect('referral_center')
        except User.DoesNotExist:
            messages.error(request, "كود غير صحيح.")

    return render(request, 'store/referral_center.html', {
        'is_eligible': is_eligible, 'grace_hours': grace_hours
    })


def legal_document(request, doc_type, user_type):
    documents = TermsAndCondition.objects.filter(document_type=doc_type, user_type=user_type).order_by('order')
    title_base = "الشروط والأحكام" if doc_type == 'TERMS' else "سياسة الخصوصية"
    target_audience = "للتجار" if user_type == 'MERCHANT' else "للعملاء"
    page_title = f"{title_base} ({target_audience})"
    return render(request, 'store/legal_page.html', {'documents': documents, 'page_title': page_title})


def about_us(request):
    about, created = AboutUs.objects.get_or_create(id=1)
    return render(request, 'store/about_us.html', {'about': about})


@login_required
def submit_review(request, product_id):
    if request.method == 'POST':
        try:
            stars = int(request.POST.get('rating', 0))
            comment = request.POST.get('comment', '')
            product = get_object_or_404(Product, id=product_id)

            if stars < 1 or stars > 5:
                messages.error(request, "يرجى اختيار تقييم من 1 إلى 5 نجوم.")
                return redirect(request.META.get('HTTP_REFERER'))

            ProductReview.objects.update_or_create(
                user=request.user, product=product,
                defaults={'rating': stars, 'comment': comment}
            )
            
            # 🔥 إشعار التاجر بالتقييم الجديد
            try:
                send_notification(
                    user=product.merchant.user, title="تقييم جديد! 🌟",
                    message=f"حصل منتجك '{product.name}' على تقييم {stars} نجوم.", link=f"/merchant/products/" 
                )
                send_push_to_user(product.merchant.user, "تقييم جديد! 🌟", f"في عميل إدى منتجك '{product.name}' {stars} نجوم.")
            except: pass
            
            messages.success(request, "شكراً لك! تم حفظ تقييمك بنجاح 🌟")
        except Exception as e:
            messages.error(request, "حدث خطأ أثناء إرسال التقييم.")
            
    return redirect(request.META.get('HTTP_REFERER', 'home'))


def customer_privacy_policy(request):
    policies = TermsAndCondition.objects.filter(
        document_type=TermsAndCondition.DocType.PRIVACY, 
        user_type=TermsAndCondition.UserType.CUSTOMER,
        is_active=True
    ).order_by('order')
    
    context = {
        'policies': policies
    }
    return render(request, 'store/privacy_policy.html', context)

