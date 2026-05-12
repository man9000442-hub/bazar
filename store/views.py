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
from django.db.models import F, Q, Case, When, Value, IntegerField
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

# الموديلات الأساسية
from accounts.models import User, Country 
from .models import (
    Product, Category, Order, OrderItem, ProductSize, 
    Wallet, WalletTransaction, MerchantProfile, Governorate, 
    MerchantShippingRate, SiteSetting, Favorite, Offer, 
    WalletDepositTransaction, Notification, Banner, DeliveryComplaint, 
    ProductReview, PersonalVoucher, AboutUs, TermsAndCondition
)

# مدير بوابات الدفع (تجريد العمليات)
from .paymob_utils import PaymobManager
from .fawaterk__utils import FawaterkManager

# دوال الإشعارات
from store.utils import send_notification, notify_admins, send_push_to_user

# ==========================================
# 2. دوال معالجة أخطاء الصفحات (Error Handlers)
# ==========================================
def custom_404_view(request, exception):
    return render(request, 'errors/404.html', status=404)

def custom_500_view(request):
    return render(request, 'errors/500.html', status=500)

# ==========================================
# 3. الدوال المساعدة (النظام الدولي والتحقق)
# ==========================================
def get_user_country(request):
    """تحديد دولة المستخدم بدقة مع اختيار تلقائي إذا كانت هناك دولة واحدة نشطة فقط"""
    # 1. إذا كان المستخدم مسجلاً وله دولة مختارة مسبقاً
    if request.user.is_authenticated and request.user.country:
        return request.user.country
        
    # 2. إذا كانت الدولة محفوظة في الجلسة (Session) للزوار
    country_id = request.session.get('user_country_id')
    if country_id:
        country = Country.objects.filter(id=country_id, is_active=True).first()
        if country:
            return country

    # 3. 🔥 التعديل المطلوب: فحص عدد الدول النشطة في النظام
    active_countries = Country.objects.filter(is_active=True)
    active_count = active_countries.count()

    if active_count == 1:
        # إذا وجدنا دولة واحدة فقط نشطة، نختارها تلقائياً
        single_country = active_countries.first()
        
        # حفظ الاختيار في الجلسة (Session) فوراً لضمان عدم تكرار الفحص
        request.session['user_country_id'] = single_country.id
        
        # إذا كان المستخدم مسجلاً، نحدث بياناته أيضاً
        if request.user.is_authenticated:
            request.user.country = single_country
            request.user.save(update_fields=['country'])
            
        return single_country
            
    # إذا كان هناك أكثر من دولة، نرجع None ليتم توجيهه لصفحة الاختيار (حسب منطق مشروعك)
    return None

def set_user_country(request):
    """تغيير دولة التسوق للزوار أو المستخدمين"""
    if request.method == 'POST':
        country_id = request.POST.get('country_id')
        if country_id and Country.objects.filter(id=country_id, is_active=True).exists():
            request.session['user_country_id'] = int(country_id)
            if request.user.is_authenticated:
                request.user.country_id = int(country_id)
                request.user.save()
            messages.success(request, _("تم تغيير دولة المتجر بنجاح."))
    return redirect(request.META.get('HTTP_REFERER', 'home'))

def check_pending_confirmations(user):
    """التحقق من وجود طلبات تتطلب تأكيد الاستلام من العميل"""
    if not user.is_authenticated: 
        return None
    pending = Order.objects.filter(
        customer=user, 
        status__in=[Order.Status.DELIVERED, Order.Status.RETURNED], 
        is_confirmed_by_customer__isnull=True
    ).first()
    return pending

# ==========================================
# 4. دوال المتجر وعرض المنتجات (Store Views)
# ==========================================
def home(request):
    """الصفحة الرئيسية للمتجر"""
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
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
        country=current_country
    )
    
    today = django_tz.now().date()
    query = request.GET.get('q')
    category_id = request.GET.get('category')
    
    # فلترة المنتجات بناءً على الدولة الصارمة وحالة التاجر
    products = Product.objects.filter(
        merchant__user__country=current_country, 
        is_active=True,
        is_approved=True,
        merchant__user__is_active=True,
        merchant__user__is_banned=False
    ).filter(
        Q(merchant__subscription_end_date__isnull=True) | Q(merchant__subscription_end_date__gte=today)
    ).filter(
        merchant__wallet__balance__gte=F('merchant__minimum_balance_required')
    )

    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category_id:
        products = products.filter(category_id=category_id)
        
    # ترتيب المنتجات بناءً على رتبة التوثيق الخاصة بالتاجر
    products = products.annotate(
        rank_weight=Case(
            When(merchant__verification_rank='GOLD', then=Value(1)),
            When(merchant__verification_rank='BLUE', then=Value(2)),
            When(merchant__verification_rank='SILVER', then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by('rank_weight', '-created_at')

    # جلب العروض النشطة في دولة المستخدم
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
    """تفاصيل المنتج مع التحقق من الدولة"""
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
        
    product = get_object_or_404(Product, pk=pk)
    current_country = get_user_country(request)
    
    if product.merchant.user.country != current_country:
        messages.error(request, _("هذا المنتج غير متوفر في دولتك الحالية."))
        return redirect('home')

    variations = product.variations.filter(stock_quantity__gt=0)
    available_colors = set(v.color_label for v in variations)
    
    variants_data = defaultdict(list)
    for v in variations:
        variants_data[v.color_label].append({
            'id': v.id, 'size': v.size_label, 'qty': v.stock_quantity
        })

    variants_json = json.dumps(dict(variants_data))

    similar_products = Product.objects.filter(
        merchant__user__country=current_country,
        category=product.category,
        is_active=True,
        is_approved=True
    ).exclude(id=product.id)[:5]
    
    is_fav = has_purchased = False
    
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
    """صفحة الأقسام الرئيسية"""
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
    categories = Category.objects.all()
    return render(request, 'store/categories.html', {'categories': categories})

def merchant_shop(request, merchant_id):
    """صفحة منتجات متجر معين (متجر التاجر)"""
    merchant = get_object_or_404(MerchantProfile, pk=merchant_id)
    current_country = get_user_country(request)
    
    if merchant.user.country != current_country:
        messages.error(request, _("هذا المتجر غير متاح في دولتك الحالية."))
        return redirect('home')
        
    products = Product.objects.filter(merchant=merchant, is_active=True).order_by('-created_at')
    return render(request, 'store/merchant_shop.html', {
        'merchant': merchant, 'products': products,
    })


def all_offers_page(request):
    """صفحة العروض الشاملة مع فلاتر أمنية قوية"""
    user_country = get_user_country(request)
    today = timezone.now().date()
    
    if not user_country:
        return render(request, 'store/all_offers.html', {'offers': [], 'page_title': _("أقوى العروض والخصومات")})
    
    active_offers = Offer.objects.filter(
        is_active=True,
        end_date__gte=timezone.now(),
        product__is_active=True,
        product__is_approved=True,
        product__merchant__user__is_active=True,
        product__merchant__user__is_banned=False,
        product__merchant__user__country=user_country,
        product__merchant__wallet__balance__gte=F('product__merchant__minimum_balance_required')
    ).filter(
        Q(product__merchant__subscription_end_date__isnull=True) | 
        Q(product__merchant__subscription_end_date__gte=today)
    ).select_related('product', 'product__merchant__user').order_by('-discount_percentage')

    return render(request, 'store/all_offers.html', {
        'offers': active_offers,
        'page_title': _("أقوى العروض والخصومات")
    })

# ==========================================
# 5. السلة وإتمام الطلب (Cart & Checkout)
# ==========================================
@login_required
def add_to_cart(request, pk):
    """إضافة منتج إلى السلة"""
    if request.method == 'POST':
        size_id = request.POST.get('size_id')
        quantity = request.POST.get('quantity', 1)
        
        if not size_id:
            messages.error(request, _("الرجاء اختيار المقاس واللون."))
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        product_size = get_object_or_404(ProductSize, pk=size_id)
        product = product_size.product 
        
        current_country = get_user_country(request)
        if product.merchant.user.country != current_country:
            messages.error(request, _("لا يمكنك إضافة منتجات من دولة أخرى لسلتك الحالية."))
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        quantity = int(quantity)
        if quantity > product_size.stock_quantity:
            messages.error(request, _("عفواً، الكمية المتاحة حالياً هي %(qty)s فقط.") % {'qty': product_size.stock_quantity})
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
            messages.success(request, _("تمت الإضافة للسلة بنجاح! 🛍️"))
            return redirect(request.META.get('HTTP_REFERER', 'home'))

        except ValidationError as e:
            error_message = ' '.join(e.messages) if hasattr(e, 'messages') else str(e)
            error_message = error_message.replace("['", "").replace("']", "")
            messages.error(request, error_message)
            return redirect(request.META.get('HTTP_REFERER', 'home'))

    return redirect('home')

@login_required
def cart_view(request):
    """عرض محتويات السلة"""
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/dashboard.html')
    
    order = Order.objects.filter(customer=request.user, status=Order.Status.CART).first()
    personal_vouchers = PersonalVoucher.objects.filter(customer=request.user, is_used=False, expires_at__gt=django_tz.now())
    
    if order:
        current_country = get_user_country(request)
        invalid_items = order.items.exclude(merchant__user__country=current_country)
        if invalid_items.exists():
            invalid_items.delete()
            messages.warning(request, _("تم إزالة بعض المنتجات من السلة لأنها غير متاحة في دولتك الحالية."))

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
    """إزالة منتج من السلة"""
    item = get_object_or_404(OrderItem, id=item_id, order__customer=request.user, order__status=Order.Status.CART)
    item.delete()
    return redirect('cart_view')

@login_required
def update_cart_qty(request, item_id, action):
    """تحديث كمية منتج في السلة"""
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
    """إتمام عملية الشراء ومعالجة الدفع وبناء الطلبات النهائية (باستخدام Services)"""
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
        messages.warning(request, _("لم تختر منتجات."))
        return redirect('cart_view')

    current_country = get_user_country(request)
    governorates = Governorate.objects.filter(country=current_country)
    settings_obj = SiteSetting.objects.filter(country=current_country).first() or SiteSetting.objects.first()

    grouped_items = defaultdict(list)
    merchant_totals = defaultdict(int)
    
    limit_pct = settings_obj.referral_discount_limit_pct if settings_obj else 10
    max_discount_amount = settings_obj.referral_discount_max_amount if settings_obj else Decimal('100.00')
    
    total_max_discount_from_pct = Decimal('0.00') 
    
    for item in cart_items:
        merch = item.product_size.product.merchant
        grouped_items[merch].append(item)
        price = Decimal(item.price_at_purchase)
        qty = item.quantity
        merchant_totals[merch] += price * qty
        total_max_discount_from_pct += (price * Decimal(limit_pct) / Decimal('100.0')) * qty

    user_balance = request.user.referral_balance
    applicable_discount = min(user_balance, total_max_discount_from_pct, max_discount_amount)

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
            messages.error(request, _("البيانات ناقصة."))
            return redirect('checkout')

        gov = get_object_or_404(Governorate, pk=gov_id, country=current_country)
        created_orders = []
        
        remaining_discount = applicable_discount if use_wallet else Decimal(0)
        total_discount_used = Decimal(0)
        is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
        
        has_free_voucher = applied_voucher.free_shipping if applied_voucher else False
        
        recipient_name = request.POST.get('recipient_name', '').strip()
        if not recipient_name:
            recipient_name = f"{request.user.first_name} {request.user.last_name}"

        if applied_voucher:
            voucher_discount_pct = Decimal(applied_voucher.discount_percentage) / Decimal(100)
            voucher_max_discount = Decimal(applied_voucher.max_discount_amount)
            voucher_items_left = applied_voucher.remaining_items
            voucher_discount_accumulated = Decimal(0)

        from store.services import OrderService

        try:
            with transaction.atomic():
                for group in cart_structure:
                    merchant = group['merchant']
                    items = group['items']
                    
                    shipping_cost, is_free_offer = OrderService.calculate_merchant_shipping(
                        merchant, gov, items, is_first_order, has_free_voucher
                    )

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
                        shipping_address=f"{gov.name} - {address}", governorate=gov, 
                        country=current_country, shipping_phone=phone,
                        payment_method=payment_method, status=initial_status, shipping_cost=shipping_cost,
                        is_first_order=(shipping_cost == 0 and not is_free_offer and not has_free_voucher),
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

                    if payment_method == 'COD':
                        try:
                            send_notification(
                                user=merchant.user, title=_("طلب جديد! 🛍️"),
                                message=_("وصلك طلب جديد #%(id)s من %(name)s.") % {'id': new_order.order_id, 'name': new_order.recipient_name},
                                link=f"/merchant/order/{new_order.order_id}/"
                            )
                            send_push_to_user(
                                user=merchant.user, title=_("طلب جديد! 🛍️"),
                                body=_("وصلك طلب جديد #%(id)s من %(name)s.") % {'id': new_order.order_id, 'name': new_order.recipient_name}
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
            import traceback
            print(f"Checkout Error: {traceback.format_exc()}") 
            messages.error(request, _("حدث خطأ أثناء إتمام الطلب، يرجى المحاولة مرة أخرى."))
            return redirect('checkout')

        # معالجة الدفع الإلكتروني عبر البوابات المتاحة
        if payment_method in ['ONLINE', 'WALLET']:
            try:
                active_gateway = getattr(settings_obj, 'active_payment_gateway', 'PAYMOB') if settings_obj else 'PAYMOB'
                
                total_to_pay = 0.0
                for o in created_orders:
                    # 🔥 الحل السحري: تحميل الأسعار الحقيقية من قاعدة البيانات بعد الـ Signals
                    o.refresh_from_db()

                    o_base_total = (o.total_products_price + o.shipping_cost) - getattr(o, 'admin_discount', Decimal('0.00'))
                    o_fees = OrderService.calculate_gateway_fees(o_base_total, current_country)
                    
                    o.platform_fees = o_fees
                    o.final_total = o_base_total + o_fees
                    o.payment_gateway_used = active_gateway
                    o.save()
                    
                    total_to_pay += float(o.final_total)

                if active_gateway == 'PAYMOB':
                    paymob = PaymobManager()
                    token = paymob.get_token()
                    amount_cents = int(total_to_pay * 100)
                    gateway_invoice_id = paymob.create_order(token, amount_cents)
                    
                    for o in created_orders:
                        o.gateway_order_id = str(gateway_invoice_id)
                        o.save()
                    
                    name_parts = recipient_name.split(' ', 1)
                    billing_data = {
                        "first_name": name_parts[0] if name_parts else (request.user.first_name or "G"), 
                        "last_name": name_parts[1] if len(name_parts) > 1 else (request.user.last_name or "U"),
                        "email": request.user.email or "no@mail.com", "phone_number": phone,
                        "city": gov.name, "country": current_country.code if current_country else "EG", 
                        "state": "NA", "street": "NA", "building": "NA", "floor": "NA", "apartment": "NA", 
                        "postal_code": "NA", "shipping_method": "NA"
                    }

                    if payment_method == 'ONLINE':
                        payment_key = paymob.get_payment_key(token, gateway_invoice_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
                        iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
                        return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})
                    
                    elif payment_method == 'WALLET':
                        if not wallet_number:
                            messages.error(request, _("رقم المحفظة مطلوب."))
                            return redirect('my_orders')
                        billing_data['phone_number'] = wallet_number 
                        redirect_url = paymob.pay_with_wallet(token, amount_cents, gateway_invoice_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
                        return redirect(redirect_url)

                elif active_gateway == 'FAWATERK':
                    fawaterk = FawaterkManager()
                    
                    name_parts = recipient_name.strip().split(' ', 1)
                    f_name = name_parts[0].strip() if len(name_parts) > 0 else (request.user.first_name or "Customer")
                    l_name = name_parts[1].strip() if len(name_parts) > 1 else (request.user.last_name or "User")
                    
                    if len(f_name) < 2: f_name = "Customer"
                    if len(l_name) < 2: l_name = "User"

                    cust_info = {
                        "first_name": f_name,
                        "last_name": l_name,
                        "email": request.user.email or "guest@domain.com",
                        "phone": phone,
                        "address": f"{gov.name} - {address}"
                    }
                    
                    items_summary = [{"name": f"Orders #{created_orders[0].order_id}", "price": float(total_to_pay), "quantity": 1}]
                    
                    success, data = fawaterk.create_invoice(
                        cart_total=total_to_pay, 
                        customer_data=cust_info, 
                        cart_items=items_summary, 
                        order_id=created_orders[0].order_id
                    )
                    
                    if success:
                        inv_id = data.get('invoice_id') or data.get('invoiceId') or data.get('id')
                        inv_url = data.get('url') or data.get('payment_url')
                        
                        for o in created_orders:
                            o.gateway_order_id = str(inv_id)
                            o.save()
                            
                        print(f"🚀 CHECKOUT INVOICE SAVED: Fawaterk Invoice: {inv_id}")
                        return redirect(inv_url)
                    else:
                        messages.error(request, _("حدث خطأ أثناء إصدار فاتورة الدفع: ") + str(data))
                        return redirect('my_orders')

            except Exception as e:
                import traceback
                print(f"Payment Gateway Error: {traceback.format_exc()}")
                messages.error(request, _("فشل الاتصال بالبنك. تم حفظ الطلب، يرجى المحاولة من 'طلباتي'."))
                return redirect('my_orders')
        
        else:
            try:
                send_notification(
                    user=request.user, title=_("تم استلام طلبك! 🎉"),
                    message=_("تم استلام طلبك بنجاح وسيقوم التاجر بتأكيده قريباً."),
                    link="/my-orders/"
                )
                send_push_to_user(
                    user=request.user, title=_("تم استلام طلبك! 🎉"),
                    body=_("تم استلام طلبك بنجاح وسيقوم التاجر بالبدء في تجهيزه.")
                )
            except: pass
            messages.success(request, _("تم استلام طلبك بنجاح!"))
            return redirect('order_success')

    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0

    personal_vouchers = PersonalVoucher.objects.filter(
        customer=request.user, is_used=False, expires_at__gt=django_tz.now() 
    )

    active_gateway = getattr(settings_obj, 'active_payment_gateway', 'PAYMOB') if settings_obj else 'PAYMOB'

    return render(request, 'store/checkout.html', {
        'cart_structure': cart_structure, 'governorates': governorates,
        'cart_total': cart_total_display, 'selected_ids': selected_ids,
        'fee_fixed': fee_fixed, 'fee_percent': fee_percent,
        'applicable_discount': applicable_discount, 'personal_vouchers': personal_vouchers,
        'current_country': current_country,
        'active_gateway': active_gateway
    })


@login_required
def retry_payment(request, order_id):
    """إعادة محاولة الدفع لطلب غير مدفوع وتحديد البوابة آلياً بدقة متناهية"""
    order = get_object_or_404(Order, pk=order_id, customer=request.user, status=Order.Status.WAITING_PAYMENT)
    
    # 🔥 الحساب الحتمي للسعر الأساسي (منعاً لتراكم الرسوم السابقة أو قراءة قيم ملوثة)
    base_total = (order.total_products_price + order.shipping_cost) - getattr(order, 'admin_discount', Decimal('0.00'))
    
    current_country = get_user_country(request)
    settings_obj = SiteSetting.objects.filter(country=current_country).first() or SiteSetting.objects.first()
    
    from store.services import OrderService
    
    if request.method == 'POST':
        method = request.POST.get('payment_method')
        wallet_number = request.POST.get('wallet_number')
        
        try:
            if method == 'COD':
                order.payment_method = 'COD'
                order.status = Order.Status.PENDING 
                order.platform_fees = Decimal('0.00') 
                order.final_total = base_total 
                order.save()
                
                try:
                    send_notification(user=order.customer, title=_("تغيير طريقة الدفع! 🔄"), message=_("تم تغيير طريقة الدفع للطلب #%(id)s إلى كاش.") % {'id': order.order_id}, link="/my-orders/")
                    send_notification(user=order.merchant.user, title=_("طلب جديد (كاش)! 🛍️"), message=_("تغيرت طريقة الدفع للطلب #%(id)s لكاش.") % {'id': order.order_id}, link=f"/merchant/order/{order.order_id}/")
                except: pass
                messages.success(request, _("تم تحويل الطلب إلى الدفع عند الاستلام بنجاح."))
                return redirect('customer_order_detail', order_id=order.id) 
            
            elif method in ['ONLINE', 'WALLET']:
                active_gateway = getattr(settings_obj, 'active_payment_gateway', 'PAYMOB') if settings_obj else 'PAYMOB'
                
                # إعادة الحساب للرسوم الدقيقة لهذا الطلب فقط باستخدام الـ Service
                online_fees = OrderService.calculate_gateway_fees(base_total, current_country)
                
                order.platform_fees = online_fees
                order.final_total = base_total + online_fees
                order.payment_method = method
                order.payment_gateway_used = active_gateway
                order.save()

                total_to_pay = float(order.final_total)

                if active_gateway == 'PAYMOB':
                    paymob = PaymobManager()
                    token = paymob.get_token()
                    amount_cents = int(total_to_pay * 100)
                    gateway_invoice_id = paymob.create_order(token, amount_cents)

                    order.gateway_order_id = str(gateway_invoice_id)
                    order.save()
                    
                    billing_data = {
                        "first_name": request.user.first_name or "Customer", "last_name": request.user.last_name or "User",
                        "email": request.user.email or "retry@pay.com", "phone_number": order.shipping_phone,
                        "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
                        "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", 
                        "country": current_country.code if current_country else "EG", "state": "NA"
                    }

                    if method == 'ONLINE':
                        payment_key = paymob.get_payment_key(token, gateway_invoice_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
                        iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
                        return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})
                    elif method == 'WALLET':
                        if not wallet_number: return redirect('retry_payment', order_id=order.id)
                        billing_data['phone_number'] = wallet_number
                        redirect_url = paymob.pay_with_wallet(token, amount_cents, gateway_invoice_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
                        return redirect(redirect_url)

                elif active_gateway == 'FAWATERK':
                    fawaterk = FawaterkManager()
                    
                    safe_recipient_name = order.recipient_name or ""
                    name_parts = safe_recipient_name.strip().split(' ', 1)
                    
                    f_name = name_parts[0].strip() if len(name_parts) > 0 else (request.user.first_name or "Customer")
                    l_name = name_parts[1].strip() if len(name_parts) > 1 else (request.user.last_name or "User")
                    
                    if len(f_name) < 2: f_name = "Customer"
                    if len(l_name) < 2: l_name = "User"

                    cust_info = {
                        "first_name": f_name,
                        "last_name": l_name,
                        "email": request.user.email or "guest@domain.com",
                        "phone": order.shipping_phone,
                        "address": order.shipping_address or "Cairo, EG"
                    }
                    
                    items_summary = [{"name": f"Order #{order.order_id}", "price": total_to_pay, "quantity": 1}]
                    
                    success, data = fawaterk.create_invoice(
                        cart_total=total_to_pay, 
                        customer_data=cust_info, 
                        cart_items=items_summary, 
                        order_id=order.order_id
                    )
                    
                    if success:
                        inv_id = data.get('invoice_id') or data.get('invoiceId') or data.get('id')
                        inv_url = data.get('url') or data.get('payment_url')
                        
                        order.gateway_order_id = str(inv_id)
                        order.save()
                        
                        print(f"🚀 INVOICE SAVED TO DB: Order #{order.order_id} -> Fawaterk Invoice: {inv_id}")
                        
                        return redirect(inv_url)
                    else:
                        messages.error(request, _("حدث خطأ أثناء إصدار فاتورة الدفع: ") + str(data))
                        return redirect('retry_payment', order_id=order.id)

        except Exception as e:
            messages.error(request, _("حدث خطأ أثناء الاتصال بالبنك، يرجى المحاولة مرة أخرى."))
            return redirect('retry_payment', order_id=order.id)

    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0
    active_gateway = getattr(settings_obj, 'active_payment_gateway', 'PAYMOB') if settings_obj else 'PAYMOB' 

    return render(request, 'store/retry_payment.html', {
        'order': order, 'base_total': float(base_total),
        'fee_fixed': fee_fixed, 'fee_percent': fee_percent,'active_gateway': active_gateway
    })


# ==========================================
# 6. المتابعة، الاسترجاع وتأكيد التسليم
# ==========================================
@login_required
def confirm_delivery_view(request, order_id):
    """تأكيد استلام الطلب أو رفع شكوى"""
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    
    if request.method == 'POST':
        action = request.POST.get('action') 
        
        if order.status == Order.Status.DELIVERED:
            if action == 'confirm':
                order.is_confirmed_by_customer = True
                try: rating_val = int(request.POST.get('rating', 5))
                except ValueError: rating_val = 5
                    
                review_comment = request.POST.get('review_comment', '').strip()
                final_comment = review_comment if review_comment else _("تقييم مجمع من الطلب #%(id)s") % {'id': order.order_id or order.id}
                
                order.rating = rating_val
                order.save()
                from store.services import OrderService
                OrderService.apply_merchant_cashback(order) # 🔥 تفعيل الكاش باك
                
                for item in order.items.all():
                    product = item.product_size.product
                    ProductReview.objects.update_or_create(
                        product=product, user=request.user, 
                        defaults={'rating': rating_val, 'comment': final_comment}
                    )
                    if hasattr(product, 'update_average_rating'): product.update_average_rating()

                try:
                    send_notification(
                        user=order.merchant.user, title=_("تأكيد استلام وتقييم! ⭐️"),
                        message=_("أكد العميل استلام الطلب #%(id)s وقيمه بـ %(rt)s نجوم.") % {'id': order.order_id, 'rt': rating_val},
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, _("استلام وتقييم ⭐️"), _("العميل استلم الطلب #%(id)s واداك %(rt)s نجوم!") % {'id': order.order_id, 'rt': rating_val})
                except: pass
                
                messages.success(request, _("شكراً لك! تم تأكيد استلامك وتقييم المنتجات بنجاح."))
                return redirect('home')
                
            elif action == 'reject':
                whatsapp_number = request.POST.get('whatsapp_number', '').strip()
                reason = request.POST.get('reason', _('التاجر يدعي التسليم، ولكنني لم أستلم الطلب أو قمت بإرجاعه للمندوب!'))
                
                if not whatsapp_number or len(whatsapp_number) < 11:
                    messages.error(request, _("يجب إدخال رقم واتساب صحيح لا يقل عن 11 رقماً."))
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
                
                try:
                    send_notification(
                        user=order.merchant.user, title=_("شكوى بعدم الاستلام! ⚠️"),
                        message=_("فتح العميل شكوى لعدم استلام الطلب #%(id)s. تم إيقاف أرباح الطلب للمراجعة.") % {'id': order.order_id},
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, _("تحذير: شكوى عدم استلام ⚠️"), _("العميل فتح شكوى بعدم استلام الطلب #%(id)s.") % {'id': order.order_id})
                except: pass

                messages.warning(request, _("تم تسجيل شكواك بعدم الاستلام! أوقفنا أرباح الطلب وسنحقق فوراً."))
                return redirect('my_orders')

        elif order.status == Order.Status.RETURNED:
            if action == 'confirm':
                order.is_confirmed_by_customer = True
                order.save()
                
                DeliveryComplaint.objects.update_or_create(
                    order=order, defaults={
                        'customer': request.user, 
                        'complaint_text': _("مرتجع متفق عليه: العميل والتاجر أكدوا المرتجع. بانتظار تدخل الإدارة لتسوية الأموال (الريفاند/الشحن)."),
                        'whatsapp_number': request.user.phone_primary or _("غير محدد"), 
                        'is_resolved': False,
                    }
                )
                
                try:
                    send_notification(
                        user=order.merchant.user, title=_("تأكيد المرتجع من العميل 🔄"),
                        message=_("أكد العميل إرجاع الطلب #%(id)s. الطلب الآن لدى الإدارة لتسوية الحسابات.") % {'id': order.order_id},
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, _("العميل أكد المرتجع 🔄"), _("تم تأكيد إرجاع الطلب #%(id)s وجاري التسوية.") % {'id': order.order_id})
                except: pass

                messages.success(request, _("تم تأكيد عملية الإرجاع. الإدارة ستقوم بتسوية أموالك في أقرب وقت."))
                return redirect('home')
                
            elif action == 'reject':
                whatsapp_number = request.POST.get('whatsapp_number', '').strip()
                reason = _("المندوب يدعي أن الطلب مرتجع، لكنني استلمته ودفعت ثمنه كاملاً!")
                
                if not whatsapp_number or len(whatsapp_number) < 11:
                    messages.error(request, _("يجب إدخال رقم واتساب صحيح."))
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
                
                try:
                    send_notification(
                        user=order.merchant.user, title=_("شكوى خطيرة! 🚨"),
                        message=_("العميل يشتكي بأنه استلم الطلب #%(id)s ودفع ثمنه، رغم تسجيله كمرتجع.") % {'id': order.order_id},
                        link=f"/merchant/order/{order.order_id}/"
                    )
                    send_push_to_user(order.merchant.user, _("شكوى تلاعب! 🚨"), _("العميل يدعي استلامه ودفع ثمن الطلب #%(id)s رغم تسجيله كمرتجع.") % {'id': order.order_id})
                except: pass

                messages.warning(request, _("تم تسجيل الشكوى الخطيرة! سنتواصل معك فوراً."))
                return redirect('my_orders')

    return render(request, 'store/confirm_delivery.html', {'order': order})

from store.services import OrderService # لا تنسى الاستدعاء ده فوق في الملف

@login_required
def customer_order_detail(request, order_id):
    order = get_object_or_404(Order, pk=order_id, customer=request.user)
    
    # 1. الحساب الدقيق للمبلغ الأساسي (زي ما عملنا في الدفع بالظبط)
    base_total = (order.total_products_price + order.shipping_cost) - getattr(order, 'admin_discount', Decimal('0.00'))
    
    # 2. جلب الرسوم لو محفوظة
    expected_fees = order.platform_fees or Decimal('0.00')
    
    # 3. لو الرسوم صفر والطلب لسه قيد الدفع، نحسبها بملف الخدمات المركزي!
    if order.status == Order.Status.WAITING_PAYMENT and expected_fees == 0:
        current_country = get_user_country(request)
        expected_fees = OrderService.calculate_gateway_fees(base_total, current_country)

    return render(request, 'store/customer_order_detail.html', {
        'order': order, 
        'base_total': float(base_total),  # ضفنا دي عشان نعرض السعر الأساسي النظيف
        'expected_fees': float(expected_fees) 
    })

def order_success(request):
    return render(request, 'store/order_success.html')

@login_required
def my_orders(request):
    orders = Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).order_by('-created_at')
    return render(request, 'store/my_orders.html', {'orders': orders})

# ==========================================
# 7. واجهة الاستجابة لبوابات الدفع (Webhooks / Callbacks)
# ==========================================
@csrf_exempt
def payment_callback(request):
    """
    استقبال إشعارات الدفع (Webhooks) وتوجيهات العودة (Redirects) من Paymob و Fawaterk.
    """
    invoice_id = None
    is_success = False
    gateway_used = None
    
    # 1. استخراج البيانات بشكل آمن لتفادي أخطاء الـ Parsing
    data = {}
    if request.method == 'POST':
        try:
            if 'application/json' in request.content_type:
                data = json.loads(request.body)
            else:
                data = request.POST
        except: pass

    # ==========================================
    # 2. تحديد البوابة وقراءة حالة الدفع (Paymob أو Fawaterk)
    # ==========================================
    
    # أ- فحص إذا كان الرد من Paymob (Webhook POST)
    if data.get('type') == 'TRANSACTION' and 'obj' in data:
        obj = data['obj']
        invoice_id = str(obj.get('order', {}).get('id'))
        is_success = obj.get('success') is True
        gateway_used = 'PAYMOB'
        
    # ب- فحص إذا كان الرد من Paymob (Redirect GET للعميل)
    elif 'id' in request.GET and 'success' in request.GET and 'order' in request.GET:
        invoice_id = str(request.GET.get('order'))
        is_success = request.GET.get('success') == 'true'
        gateway_used = 'PAYMOB'

    # ج- فحص إذا كان الرد من Fawaterk (Webhook أو Redirect)
    else:
        invoice_id = data.get('invoice_id') or request.GET.get('invoice_id') or request.GET.get('order')
        if invoice_id:
            gateway_used = 'FAWATERK'

    # ==========================================

    if not invoice_id:
        if request.method == 'POST': return HttpResponse("Ignored: No Invoice ID", status=200)
        return redirect('my_orders')

    inv_str = str(invoice_id).strip()

    # 3. البحث في قاعدة البيانات (محافظ أو طلبات)
    deposit_tx = WalletDepositTransaction.objects.filter(gateway_order_id=inv_str, is_paid=False).first()
    order_tx = Order.objects.filter(gateway_order_id=inv_str).first()

    if not deposit_tx and not order_tx:
        if request.method == 'POST': return HttpResponse("Not Found", status=404)
        return redirect('my_orders')

    # تأكيد اسم البوابة من الداتابيز لو كانت ناقصة
    if not gateway_used:
        if deposit_tx: gateway_used = deposit_tx.gateway_name or 'FAWATERK'
        elif order_tx: gateway_used = order_tx.payment_gateway_used or 'FAWATERK'

    # 4. التحقق عبر الـ API (خاص بـ Fawaterk فقط لأن Paymob أرسل حالة الدفع مسبقاً في الرد)
    if gateway_used.upper() == 'FAWATERK':
        try:
            fawaterk = FawaterkManager()
            success, api_data = fawaterk.get_transaction_data(inv_str)
            if success and api_data.get('paid') == 1:
                is_success = True
            else:
                is_success = False
        except Exception as e:
            is_success = False

    # ==========================================
    # 5. تحديث قاعدة البيانات في حالة الدفع الناجح
    # ==========================================
    if is_success:
        # حالة 1: الدفع كان لشحن محفظة التاجر
        if deposit_tx:
            with transaction.atomic():
                deposit_tx.is_paid = True
                deposit_tx.save()
                
                # 🔥 إضافة الرصيد الفعلي للمحفظة وتسجيل العملية
                wallet = deposit_tx.wallet
                wallet.balance += deposit_tx.amount
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet, 
                    amount=deposit_tx.amount, 
                    transaction_type='COMPENSATION', # أو DEPOSIT حسب الموديل عندك
                    description=f"شحن رصيد إلكتروني بوابة ({gateway_used})",
                    balance_after=wallet.balance, 
                    is_released=True
                )
            if request.method == 'POST': return HttpResponse("OK", status=200)
            messages.success(request, _("تم شحن محفظتك بنجاح!"))
            return redirect('merchant_wallet') # تأكد من اسم الـ url الخاص بمحفظة التاجر

        # حالة 2: الدفع كان لطلبات شراء
        if order_tx:
            pending_orders = Order.objects.filter(gateway_order_id=inv_str, status=Order.Status.WAITING_PAYMENT)
            if pending_orders.exists():
                with transaction.atomic():
                    for order in pending_orders:
                        order.status = Order.Status.PENDING # تم الدفع، في انتظار التاجر
                        order.save()
                        
                        # إرسال إشعارات للتاجر بأن الطلب تم دفعه!
                        try:
                            send_notification(
                                user=order.merchant.user, title=_("طلب مدفوع جديد! 💳"),
                                message=_("تم استلام مبلغ الطلب #%(id)s، يرجى التجهيز.") % {'id': order.order_id},
                                link=f"/merchant/order/{order.order_id}/"
                            )
                        except: pass
                        
            if request.method == 'POST': return HttpResponse("OK", status=200)
            messages.success(request, _("تم تأكيد الدفع بنجاح! شكراً لتسوقك معنا."))
            return redirect('order_success') # توجيه لصفحة النجاح بدلاً من الطلبات

    # إذا الدفع لم ينجح أو تم الإلغاء
    if request.method == 'POST': return HttpResponse("Ignored or Failed", status=200)
    messages.error(request, _("لم يتم تأكيد الدفع أو تم إلغاؤه."))
    return redirect('my_orders')


from store.services import OrderService # 👈 استدعاء ملف الخدمات السحري

@login_required
def calculate_shipping_api(request):
    """إرجاع بيانات تكلفة الشحن آلياً بتنسيق JSON للواجهات"""
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
    
    items_by_merchant = defaultdict(list)
    total_products_price = Decimal('0.00')
    for item in cart_items:
        items_by_merchant[item.product_size.product.merchant].append(item)
        total_products_price += item.price_at_purchase * item.quantity

    is_first_order = not Order.objects.filter(customer=request.user).exclude(status=Order.Status.CART).exists()
    
    shipping_details = []
    total_shipping = Decimal('0.00')

    # 🚀 هنا السحر: حساب الشحن بسطر واحد من الـ Service لكل تاجر!
    for merchant, items in items_by_merchant.items():
        cost, _ = OrderService.calculate_merchant_shipping(merchant, governorate, items, is_first_order)
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
    current_country = get_user_country(request)
    settings_obj = SiteSetting.objects.filter(country=current_country).first() or SiteSetting.objects.first()
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
                messages.error(request, _("لا يمكنك دعوة نفسك!"))
            elif user.invited_by:
                messages.error(request, _("لقد استخدمت كود دعوة مسبقاً."))
            else:
                user.invited_by = inviter
                user.save()
                
                try:
                    send_notification(
                        user=inviter, title=_("دعوة ناجحة! 🎉"),
                        message=_("قام %(name)s باستخدام كود دعوتك. ستحصل على المكافأة عند أول شراء له.") % {'name': user.first_name}, link="/referral-center/"
                    )
                    send_push_to_user(inviter, _("مبروك دعوة ناجحة! 🎉"), _("%(name)s سجل بكودك، هينزلك مكافأة أول ما يشتري.") % {'name': user.first_name})
                except: pass
                
                messages.success(request, _("تم تفعيل كود الدعوة بنجاح! 🎉"))
                return redirect('referral_center')
        except User.DoesNotExist:
            messages.error(request, _("كود غير صحيح."))

    return render(request, 'store/referral_center.html', {
        'is_eligible': is_eligible, 'grace_hours': grace_hours
    })

def legal_document(request, doc_type, user_type):
    current_country = get_user_country(request)
    # 🔥 فلترة الشروط والأحكام حسب دولة المستخدم أو الشروط العامة (التي ليس لها دولة)
    documents = TermsAndCondition.objects.filter(
        document_type=doc_type, 
        user_type=user_type,
        is_active=True
    ).filter(
        Q(country=current_country) | Q(country__isnull=True)
    ).order_by('order')
    
    title_base = _("الشروط والأحكام") if doc_type == 'TERMS' else _("سياسة الخصوصية")
    target_audience = _("للتجار") if user_type == 'MERCHANT' else _("للعملاء")
    page_title = f"{title_base} ({target_audience})"
    return render(request, 'store/legal_page.html', {'documents': documents, 'page_title': page_title})

def about_us(request):
    current_country = get_user_country(request)
    about = AboutUs.objects.filter(country=current_country).first()
    if not about:
        about = AboutUs.objects.filter(country__isnull=True).first()
    return render(request, 'store/about_us.html', {'about': about})

@login_required
def submit_review(request, product_id):
    if request.method == 'POST':
        try:
            stars = int(request.POST.get('rating', 0))
            comment = request.POST.get('comment', '')
            product = get_object_or_404(Product, id=product_id)

            if stars < 1 or stars > 5:
                messages.error(request, _("يرجى اختيار تقييم من 1 إلى 5 نجوم."))
                return redirect(request.META.get('HTTP_REFERER'))

            ProductReview.objects.update_or_create(
                user=request.user, product=product,
                defaults={'rating': stars, 'comment': comment}
            )
            
            try:
                send_notification(
                    user=product.merchant.user, title=_("تقييم جديد! 🌟"),
                    message=_("حصل منتجك '%(name)s' على تقييم %(stars)s نجوم.") % {'name': product.name, 'stars': stars}, link=f"/merchant/products/" 
                )
                send_push_to_user(product.merchant.user, _("تقييم جديد! 🌟"), _("في عميل إدى منتجك '%(name)s' %(stars)s نجوم.") % {'name': product.name, 'stars': stars})
            except: pass
            
            messages.success(request, _("شكراً لك! تم حفظ تقييمك بنجاح 🌟"))
        except Exception as e:
            messages.error(request, _("حدث خطأ أثناء إرسال التقييم."))
            
    return redirect(request.META.get('HTTP_REFERER', 'home'))

def customer_privacy_policy(request):
    current_country = get_user_country(request)
    policies = TermsAndCondition.objects.filter(
        document_type=TermsAndCondition.DocType.PRIVACY, 
        user_type=TermsAndCondition.UserType.CUSTOMER,
        is_active=True
    ).filter(
        Q(country=current_country) | Q(country__isnull=True)
    ).order_by('order')
    
    context = {
        'policies': policies
    }
    return render(request, 'store/privacy_policy.html', context)

import os
import markdown
from django.conf import settings
from django.shortcuts import render, Http404
from django.utils.safestring import mark_safe

def project_docs_view(request, doc_name):
    # خريطة بأسماء الملفات والروابط الخاصة بها
    docs_map = {
        'summary': 'md/PROJECT_SUMMARY_AR.md',
        'migration': 'md/MIGRATION_GUIDE_AR.md',
        'index': 'md/DOCUMENTATION_INDEX_AR.md',
        'completion': 'md/SUMMARY_COMPLETION.md',
    }

    if doc_name not in docs_map:
        raise Http404("Document not found")

    file_path = os.path.join(settings.BASE_DIR, docs_map[doc_name])
    
    if not os.path.exists(file_path):
        raise Http404("File not found on server")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        # تحويل المارك داون إلى HTML مع دعم الجداول والقوائم
        html_content = markdown.markdown(content, extensions=['extra', 'tables', 'toc'])

    context = {
        'doc_content': mark_safe(html_content),
        'title': docs_map[doc_name].replace('_', ' ').replace('.md', '')
    }
    return render(request, 'docs/doc_viewer.html', context)