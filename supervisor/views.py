# ==========================================
# 1. الاستدعاءات الأساسية (Imports)
# ==========================================
import csv
import json
import os
import markdown
import requests
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from django.urls import reverse, NoReverseMatch
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.crypto import get_random_string
from django.utils.safestring import mark_safe
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Count, Sum, Q, F, ProtectedError
from django.db.models.functions import TruncDay, TruncMonth
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.core.cache import cache

# الموديلات
from accounts.models import User, CustomRole, Country
from store.models import (
    Product, Order, MerchantProfile, DepositRequest, 
    WithdrawalRequest, Offer, Category, SiteSetting, OrderItem,
    ProductReview, Wallet, WalletTransaction, Notification, Banner,
    DeliveryComplaint, PersonalVoucher, AboutUs, TermsAndCondition,
    MerchantShippingRate, WalletDepositTransaction, ReturnRequest, ProductSize, ProductImage, PromoPopup, Governorate
)
from support.models import SupportTicket, TicketMessage

# ==========================================
# 🔥 إعداد دوال الإشعارات
# ==========================================
from store.utils import send_notification, notify_admins, send_push_to_user


# ==========================================
# 🔥 2. دوال مساعدة للفلترة، الترجمة، وتوليد الروابط
# ==========================================
def parse_decimal(val, default='0.00'):
    if val is None:
        return Decimal(default)
    if isinstance(val, (Decimal, int, float)):
        return Decimal(str(val))
    val_str = str(val).strip()
    if not val_str:
        return Decimal(default)
    arabic_to_english = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    val_str = val_str.translate(arabic_to_english).replace(',', '.')
    try:
        return Decimal(val_str)
    except InvalidOperation:
        return Decimal(default)

def is_supervisor(user):
    return user.is_superuser or user.role in [User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3, User.Role.COUNTRY_ADMIN, User.Role.OWNER]

def filter_by_country(user, qs):
    if user.is_superuser or str(user.role) == 'OWNER':
        return qs
    if not user.country:
        return qs.none() 
    model = qs.model
    if model == Order:
        return qs.filter(Q(customer__country=user.country) | Q(merchant__user__country=user.country)).distinct()
    elif model == Product:
        return qs.filter(merchant__user__country=user.country)
    elif model == MerchantProfile:
        return qs.filter(user__country=user.country)
    elif model == User:
        return qs.filter(country=user.country)
    elif model == SupportTicket:
        return qs.filter(customer__country=user.country)
    elif model in [DepositRequest, WithdrawalRequest, Wallet]:
        return qs.filter(merchant__user__country=user.country)
    elif model == WalletTransaction:
        return qs.filter(wallet__merchant__user__country=user.country)
    elif model in [Offer, ProductReview]:
        return qs.filter(product__merchant__user__country=user.country)
    elif model == DeliveryComplaint:
        return qs.filter(Q(customer__country=user.country) | Q(order__merchant__user__country=user.country)).distinct()
    elif model == PersonalVoucher:
        return qs.filter(customer__country=user.country)
    elif model == ReturnRequest:
        return qs.filter(Q(order__customer__country=user.country) | Q(order__merchant__user__country=user.country)).distinct()
    elif hasattr(model, 'country'):
        return qs.filter(country=user.country)
    return qs

def save_dynamic_translations(request, obj, fields):
    """حفظ الحقول المترجمة ديناميكياً بناءً على اللغات المفعلة بالنظام"""
    try:
        languages = [lang[0] for lang in settings.LANGUAGES]
    except AttributeError:
        languages = ['en', 'ar']
        
    for field in fields:
        for lang in languages:
            post_key = f"{field}_{lang}"
            if post_key in request.POST:
                setattr(obj, post_key, request.POST.get(post_key))

def get_url_safely(url_name, default_path, *args):
    """توليد رابط آمن للـ Notifications لعدم كسر النظام لو كان الاسم غير متوفر"""
    try:
        return reverse(url_name, args=args) if args else reverse(url_name)
    except NoReverseMatch:
        return default_path


# ==========================================
# 3. لوحة التحكم والإحصائيات (Dashboard)
# ==========================================
@login_required
def supervisor_dashboard(request):
    if not is_supervisor(request.user): 
        return redirect('home')
    
    # 1. منطق فلترة الوقت المطور
    range_type = request.GET.get('range', 'month')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    today = timezone.now().date()
    start_date = today.replace(day=1) # الافتراضي: أول الشهر
    end_date = today

    if range_type == 'today':
        start_date = today
    elif range_type == 'week':
        start_date = today - timedelta(days=7)
    elif range_type == 'year':
        start_date = today.replace(month=1, day=1)
    elif range_type == 'custom' and start_date_str and end_date_str:
        try:
            start_date = parse_date(start_date_str)
            end_date = parse_date(end_date_str)
        except: pass

    # 2. جلب البيانات بناءً على التاريخ والدولة
    orders_qs = filter_by_country(request.user, Order.objects.filter(created_at__date__range=[start_date, end_date]))
    
    # الإحصائيات المالية للفترة المختارة
    sales_in_range = orders_qs.filter(status__in=['PENDING', 'SHIPPED', 'DELIVERED']).aggregate(Sum('final_total'))['final_total__sum'] or 0
    
    platform_profit = abs(float(filter_by_country(request.user, WalletTransaction.objects.filter(
        created_at__date__range=[start_date, end_date],
        amount__lt=0,
        description__contains="خصم عمولة"
    )).aggregate(Sum('amount'))['amount__sum'] or 0))

    # 3. المهام المعلقة (تظهر الكل لأنها تحتاج إجراء من الإدارة)
    pending_orders = filter_by_country(request.user, Order.objects.filter(status=Order.Status.PENDING)).count()
    pending_products = filter_by_country(request.user, Product.objects.filter(is_approved=False)).count()
    
    # 🔥 تم الفصل هنا: الشكاوى لوحدها والمرتجعات لوحدها والتذاكر
    pending_returns = filter_by_country(request.user, ReturnRequest.objects.filter(status='PENDING')).count()
    pending_complaints = filter_by_country(request.user, DeliveryComplaint.objects.filter(is_resolved=False)).count()
    open_tickets_count = filter_by_country(request.user, SupportTicket.objects.filter(status='OPEN')).count()
    
    pending_withdrawals = filter_by_country(request.user, WithdrawalRequest.objects.filter(status='PENDING')).count()
    new_merchants = filter_by_country(request.user, MerchantProfile.objects.filter(is_approved=False)).count()

    # 4. بيانات الرسم البياني (حسب الفترة)
    chart_data = orders_qs.annotate(day=TruncDay('created_at')).values('day').annotate(total=Sum('final_total')).order_by('day')
    days_labels = [entry['day'].strftime("%d %b") for entry in chart_data]
    sales_values = [float(entry['total']) for entry in chart_data]

    recent_orders = orders_qs.select_related('customer', 'merchant').order_by('-created_at')[:6]

    context = {
        'sales_in_range': float(sales_in_range),
        'platform_profit': platform_profit,
        'pending_orders': pending_orders,
        'pending_products': pending_products,
        'pending_returns': pending_returns,
        'pending_complaints': pending_complaints, # تمرير عدد الشكاوى
        'open_tickets_count': open_tickets_count, # تمرير عدد التذاكر
        'pending_withdrawals': pending_withdrawals,
        'new_merchants': new_merchants,
        'recent_orders': recent_orders,
        'chart_labels': json.dumps(days_labels),
        'chart_data': json.dumps(sales_values),
        'current_range': range_type,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'supervisor/dashboard.html', context)





# ==========================================
# 4. إدارة الطلبات (Orders)
# ==========================================
@login_required
def all_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    status = request.GET.get('status')
    orders = filter_by_country(request.user, Order.objects.exclude(status=Order.Status.CART)).order_by('-created_at')
    if status: orders = orders.filter(status=status)
    return render(request, 'supervisor/all_orders.html', {'orders': orders})

@login_required
def order_detail(request, order_id):
    if not is_supervisor(request.user): return redirect('home')
    order = get_object_or_404(filter_by_country(request.user, Order.objects.all()), order_id=order_id)
    
    if request.method == 'POST' and request.user.has_perm_access('orders'):
        new_status = request.POST.get('status')
        if new_status in dict(Order.Status.choices):
            order.status = new_status
            order.save()
            
            link = get_url_safely('my_orders', '/my-orders/')
            send_notification(order.customer, "تحديث حالة الطلب 📦", f"تم تحديث حالة طلبك #{order.order_id} إلى: {order.get_status_display()}", link)
            send_push_to_user(order.customer, "تحديث الطلب 📦", f"طلبك الآن: {order.get_status_display()}")
            
            messages.success(request, f"تم تحديث حالة الطلب إلى '{order.get_status_display()}' بنجاح ✅")
            return redirect('super_order_detail', order_id=order.order_id)
            
    return render(request, 'supervisor/order_detail.html', {'order': order})

@login_required
def export_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['رقم الطلب', 'العميل', 'الهاتف', 'الإجمالي', 'الحالة', 'التاريخ'])
    orders = filter_by_country(request.user, Order.objects.exclude(status='CART')).values_list('order_id', 'customer__first_name', 'shipping_phone', 'final_total', 'status', 'created_at')
    for order in orders: writer.writerow(order)
    return response


# ==========================================
# 5. إدارة المنتجات (Products)
# ==========================================
@login_required
def all_products(request):
    if not is_supervisor(request.user): return redirect('home')
    products = filter_by_country(request.user, Product.objects.all()).annotate(
        sales_count=Count('variations__orderitem', filter=Q(variations__orderitem__order__status='DELIVERED'))
    )
    q = request.GET.get('q')
    sort = request.GET.get('sort', '-created_at')
    if q: products = products.filter(Q(name__icontains=q) | Q(merchant__user__first_name__icontains=q))
    
    if sort == 'best_selling': products = products.order_by('-sales_count')
    elif sort == 'price_high': products = products.order_by('-base_price')
    elif sort == 'price_low': products = products.order_by('base_price')
    else: products = products.order_by('-created_at')

    context = {
        'products': products, 'total_count': products.count(),
        'active_count': products.filter(is_active=True).count(),
        'top_product': products.order_by('-sales_count').first(), 'current_sort': sort
    }
    return render(request, 'supervisor/all_products.html', context)

@login_required
def pending_products(request):
    if not is_supervisor(request.user): return redirect('home')
    products = filter_by_country(request.user, Product.objects.filter(is_approved=False)).order_by('-created_at')
    return render(request, 'supervisor/pending_products.html', {'products': products})

@login_required
def product_review(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(filter_by_country(request.user, Product.objects.all()), pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            product.commission_pct = parse_decimal(request.POST.get('commission'))
            product.is_approved = True 
            
            if product.merchant.are_products_hidden:
                product.is_active = False 
                messages.warning(request, f"تم قبول المنتج '{product.name}'، ولكنه لن يظهر للعملاء لأنك قمت بإخفاء متجر هذا التاجر إدارياً.")
            else:
                product.is_active = True
                link = get_url_safely('merchant_products', '/merchant/products/')
                send_notification(product.merchant.user, "تم قبول منتجك! ✅", f"تم اعتماد منتج '{product.name}' وهو الآن معروض للبيع.", link)
                send_push_to_user(product.merchant.user, "منتج مقبول ✅", f"تمت الموافقة على منتج '{product.name}' ونشره في المتجر.")
                messages.success(request, f"تم اعتماد المنتج {product.name} وعرضه بنجاح ✅")
                
            product.save()
            
        elif action == 'reject':
            send_notification(product.merchant.user, "تم رفض المنتج ❌", f"عفواً، تم رفض منتج '{product.name}' لمخالفته شروط المنصة.")
            send_push_to_user(product.merchant.user, "منتج مرفوض ❌", f"تم رفض منتج '{product.name}' لعدم استيفاء الشروط.")
            product.delete()
            messages.error(request, "تم رفض وحذف المنتج.")
            
        return redirect('super_pending_products')
    return render(request, 'supervisor/product_review.html', {'product': product})

@login_required
def edit_product_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(filter_by_country(request.user, Product.objects.all()), pk=pk)
    if request.method == 'POST':
        product.is_active = request.POST.get('is_active') == 'on'
        product.commission_pct = parse_decimal(request.POST.get('commission'))
        product.save()
        messages.success(request, "تم تحديث المنتج.")
        return redirect('super_all_products')
    return render(request, 'supervisor/product_edit_admin.html', {'product': product})

@login_required
def delete_product_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(filter_by_country(request.user, Product.objects.all()), pk=pk)
    try:
        product_name = product.name
        merchant_user = product.merchant.user
        product.delete()
        send_notification(merchant_user, "حذف منتج إدارياً ⚠️", f"قامت الإدارة بحذف منتجك '{product_name}'.")
        send_push_to_user(merchant_user, "تنبيه إداري ⚠️", f"قامت الإدارة بحذف منتجك '{product_name}'.")
        messages.success(request, f"تم حذف المنتج '{product_name}' بنجاح ✅")
    except ProtectedError:
        product.is_active = False
        product.save()
        send_notification(product.merchant.user, "إيقاف منتج ⚠️", f"قامت الإدارة بإيقاف عرض منتجك '{product.name}'.")
        send_push_to_user(product.merchant.user, "إيقاف منتج ⚠️", f"قامت الإدارة بإيقاف عرض منتجك '{product.name}' لارتباطه بطلبات سابقة.")
        messages.warning(request, f"⚠️ تم إخفاء وتعطيل المنتج بدلاً من حذفه لارتباطه بطلبات سابقة.")
    return redirect(request.META.get('HTTP_REFERER', 'home'))


# ==========================================
# 6. إدارة التجار (Merchants)
# ==========================================
@login_required
def merchants_list(request):
    if not is_supervisor(request.user): return redirect('home')
    
    q = request.GET.get('q', '')
    rank = request.GET.get('rank', '')
    
    # جلب التجار النشطين
    base_merchants = filter_by_country(request.user, MerchantProfile.objects.filter(is_approved=True))
    
    # تطبيق البحث والفلترة
    merchants = base_merchants
    if q:
        merchants = merchants.filter(Q(user__first_name__icontains=q) | Q(user__phone_primary__icontains=q) | Q(user__last_name__icontains=q))
    if rank:
        merchants = merchants.filter(verification_rank=rank)
        
    merchants = merchants.order_by('-user__date_joined')

    # إحصائيات سريعة
    total_active = base_merchants.count()
    pending_count = filter_by_country(request.user, MerchantProfile.objects.filter(is_approved=False)).count()

    context = {
        'merchants': merchants,
        'total_active': total_active,
        'pending_count': pending_count,
    }
    return render(request, 'supervisor/merchants_list.html', context)

@login_required
def pending_merchants(request):
    if not is_supervisor(request.user): return redirect('home')
    merchants = filter_by_country(request.user, MerchantProfile.objects.filter(is_approved=False))
    return render(request, 'supervisor/pending_merchants.html', {'merchants': merchants})

@login_required
def approve_merchant(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)
    merchant.is_approved = True
    rank = request.POST.get('verification_rank', 'NONE')
    merchant.verification_rank = rank
    merchant.is_verified = True if rank != 'NONE' else False
    
    # -------- الإضافات الجديدة: استقبال الإعدادات والصلاحيات --------
    # 1. الحد الأقصى للمنتجات
    new_limit = request.POST.get('product_limit')
    if new_limit and new_limit.isdigit(): 
        merchant.product_limit = int(new_limit)
        
    # 2. الحد الأدنى للرصيد
    min_balance = request.POST.get('minimum_balance_required')
    if min_balance is not None and min_balance.strip() != '':
        merchant.minimum_balance_required = parse_decimal(min_balance)
        
    # 3. تاريخ انتهاء الاشتراك
    sub_end_date = request.POST.get('subscription_end_date')
    if sub_end_date:
        merchant.subscription_end_date = sub_end_date
    else:
        merchant.subscription_end_date = None
    # -----------------------------------------------------------------

    if request.GET.get('verify') == 'true':
        merchant.is_verified = True
        msg = f"تم تفعيل وتوثيق التاجر {merchant.user.first_name} بنجاح، وتطبيق الإعدادات المخصصة له! 🌟"
    else:
        msg = f"تم تفعيل التاجر {merchant.user.first_name} وتطبيق إعداداته بنجاح"
        
    merchant.save()
    
    link = get_url_safely('merchant_dashboard', '/merchant/dashboard/')
    send_notification(merchant.user, "تم تفعيل متجرك! 🎉", "مبروك! تمت الموافقة على متجرك ويمكنك الآن إضافة منتجاتك.", link)
    send_push_to_user(merchant.user, "مبروك تفعيل المتجر! 🎉", "تم تفعيل حسابك كتاجر، ابدأ الآن بإضافة منتجاتك.")
    messages.success(request, msg)
    return redirect('super_pending_merchants')

@login_required
def reject_merchant(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)
    user = merchant.user
    
    send_notification(user, "رفض طلب متجر ❌", "نأسف، لم يتم قبول طلب فتح المتجر لعدم استيفاء الشروط المطلوبة.")
    send_push_to_user(user, "رفض طلب التاجر ❌", "عفواً، تم رفض طلبك لفتح متجر لعدم استيفاء الشروط.")
    
    merchant.delete()
    user.role = 'CUSTOMER'
    user.save()
    messages.warning(request, f"تم رفض طلب التاجر {user.first_name} وإعادته كعميل.")
    return redirect('super_pending_merchants')

@login_required
def toggle_verify_merchant(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)
    merchant.is_verified = not merchant.is_verified
    merchant.save()
    status = "تم توثيق" if merchant.is_verified else "إلغاء توثيق"
    messages.success(request, f"{status} التاجر {merchant.user.first_name}")
    return redirect(request.META.get('HTTP_REFERER', 'super_users_list'))

@login_required
def update_merchant_limit(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)
    
    if request.method == 'POST':
        new_limit = request.POST.get('product_limit')
        if new_limit and new_limit.isdigit(): 
            merchant.product_limit = int(new_limit)
            
        merchant.subscription_end_date = request.POST.get('subscription_end_date') or None 
        
        min_balance = request.POST.get('minimum_balance_required')
        if min_balance is not None and min_balance.strip() != '':
            merchant.minimum_balance_required = parse_decimal(min_balance)
                
        merchant.save()
        messages.success(request, f"تم تحديث صلاحيات التاجر ({merchant.user.first_name}) بنجاح ✅.")
        
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def hide_merchant_products(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)
    
    merchant.are_products_hidden = True
    merchant.save()
    Product.objects.filter(merchant=merchant).update(is_active=False)
    
    send_notification(merchant.user, "إيقاف المنتجات ⚠️", "تم إيقاف عرض جميع منتجاتك إدارياً، يرجى مراجعة الدعم الفني.")
    send_push_to_user(merchant.user, "إيقاف المنتجات ⚠️", "تم إيقاف منتجاتك مؤقتاً بواسطة الإدارة.")
    messages.success(request, f"تم إخفاء منتجات التاجر وتفعيل الحظر المستمر بنجاح ✅")
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def show_merchant_products(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)
    
    merchant.are_products_hidden = False
    merchant.save()
    Product.objects.filter(merchant=merchant, is_approved=True).update(is_active=True)
    
    send_notification(merchant.user, "تفعيل المنتجات ✅", "تم إعادة تفعيل وعرض منتجاتك على المنصة بنجاح.")
    send_push_to_user(merchant.user, "تفعيل المنتجات ✅", "تم إرجاع منتجاتك للظهور على المنصة بنجاح.")
    messages.success(request, f"تم إظهار منتجات التاجر المقبولة وفك الحظر بنجاح ✅")
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def merchant_profile_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(filter_by_country(request.user, MerchantProfile.objects.all()), pk=pk)

    if request.method == 'POST':
        if 'cashback_form' in request.POST:
            from store.models import MerchantCashback
            cb_type = request.POST.get('cashback_type')
            cb_amount = parse_decimal(request.POST.get('cashback_amount'))
            cb_start = request.POST.get('cashback_start')
            cb_end = request.POST.get('cashback_end')
            cb_active = request.POST.get('cashback_active') == 'on'
            
            if cb_start and cb_end:
                MerchantCashback.objects.update_or_create(
                    merchant=merchant,
                    defaults={
                        'cashback_type': cb_type,
                        'amount': cb_amount,
                        'start_date': cb_start,
                        'end_date': cb_end,
                        'is_active': cb_active
                    }
                )
                messages.success(request, "تم حفظ إعدادات الكاش باك للتاجر بنجاح 🎁")
            else:
                messages.error(request, "يجب تحديد تاريخ البداية والنهاية.")
            return redirect('super_merchant_profile', pk=pk)
        
        merchant.goods_types = request.POST.get('goods_types')
        merchant.goods_quantity = request.POST.get('goods_quantity')
        merchant.goods_average_price = request.POST.get('goods_average_price')
        merchant.goods_sizes = request.POST.get('goods_sizes')
        merchant.national_id = request.POST.get('national_id')
        merchant.tax_register_number = request.POST.get('tax_register')
        
        rank = request.POST.get('verification_rank', 'NONE')
        merchant.verification_rank = rank
        merchant.is_verified = True if rank != 'NONE' else False
        
        if request.FILES.get('shop_image'): merchant.shop_image = request.FILES.get('shop_image')
        if request.FILES.get('id_card_front'): merchant.id_card_front = request.FILES.get('id_card_front')
        if request.FILES.get('id_card_back'): merchant.id_card_back = request.FILES.get('id_card_back')
            
        merchant.save()
        messages.success(request, "تم تحديث بيانات التاجر بنجاح ✅")
        return redirect('super_merchant_profile', pk=pk)
    
    range_type = request.GET.get('range', 'all') 
    custom_start, custom_end = request.GET.get('start'), request.GET.get('end')
    today = timezone.now().date()
    start_date, end_date = None, today

    if range_type == 'today': start_date = today
    elif range_type == 'week': start_date = today - timedelta(days=7)
    elif range_type == 'month': start_date = today.replace(day=1)
    elif range_type == 'year': start_date = today.replace(month=1, day=1)
    elif range_type == 'custom' and custom_start:
        try: start_date, end_date = parse_date(custom_start), parse_date(custom_end) or today
        except: pass

    wallet = getattr(merchant, 'wallet', None)
    tx_qs = WalletTransaction.objects.filter(wallet=wallet) if wallet else WalletTransaction.objects.none()
    successful_items_qs = OrderItem.objects.filter(product_size__product__merchant=merchant, order__status='DELIVERED')
    returned_items_qs = OrderItem.objects.filter(product_size__product__merchant=merchant, order__status='RETURNED')

    if start_date:
        tx_qs = tx_qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        successful_items_qs = successful_items_qs.filter(order__created_at__date__gte=start_date, order__created_at__date__lte=end_date)
        returned_items_qs = returned_items_qs.filter(order__created_at__date__gte=start_date, order__created_at__date__lte=end_date)

    return render(request, 'supervisor/merchant_profile_admin.html', {
        'merchant': merchant, 'wallet': wallet, 'transactions': tx_qs.order_by('-created_at'),
        'products_count': merchant.products.count(), 
        'total_sales_value': successful_items_qs.aggregate(total=Sum(F('quantity') * F('price_at_purchase')))['total'] or Decimal('0.00'),
        'total_items_sold': successful_items_qs.aggregate(total=Sum('quantity'))['total'] or 0,
        'total_return_value': returned_items_qs.aggregate(total=Sum(F('quantity') * F('price_at_purchase')))['total'] or Decimal('0.00'),
        'total_items_returned': returned_items_qs.aggregate(total=Sum('quantity'))['total'] or 0,
        'current_range': range_type, 'start_date': start_date, 'end_date': end_date,
    })


# ==========================================
# 7. إدارة المستخدمين (Users & Customers)
# ==========================================
@login_required
def users_list(request):
    if not is_supervisor(request.user): return redirect('home')
    role, q = request.GET.get('role'), request.GET.get('q')
    
    # جلب كل المستخدمين بناءً على صلاحيات المشرف
    base_users = filter_by_country(request.user, User.objects.all())
    users = base_users.order_by('-date_joined')
    
    # الفلترة
    if role: users = users.filter(role=role)
    if q: users = users.filter(Q(username__icontains=q) | Q(phone_primary__icontains=q))
    
    # حساب الإحصائيات لبطاقات العرض السطحية
    total_users = base_users.count()
    total_customers = base_users.filter(role='CUSTOMER').count()
    total_merchants = base_users.filter(role='MERCHANT').count()
    # المشرفين هم أي حد غير العميل والتاجر
    total_supervisors = base_users.exclude(role__in=['CUSTOMER', 'MERCHANT']).count()

    context = {
        'users': users,
        'total_users': total_users,
        'total_customers': total_customers,
        'total_merchants': total_merchants,
        'total_supervisors': total_supervisors,
    }
    return render(request, 'supervisor/users_list.html', context)

@login_required
def user_edit(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_obj = get_object_or_404(filter_by_country(request.user, User.objects.all()), pk=user_id)
    
    if request.method == 'POST':
        if request.POST.get('first_name'): user_obj.first_name = request.POST.get('first_name')
        if request.POST.get('last_name'): user_obj.last_name = request.POST.get('last_name')
        if request.POST.get('phone'):
            user_obj.phone_primary = request.POST.get('phone')
            user_obj.username = request.POST.get('phone') 
        if request.POST.get('email'): user_obj.email = request.POST.get('email')

        role = request.POST.get('role')
        if role: user_obj.role = role
        
        country_id = request.POST.get('country')
        if country_id:
            user_obj.country_id = country_id

        user_obj.is_active = request.POST.get('is_active') == 'on'
        user_obj.is_banned = request.POST.get('is_banned') == 'on'
        
        new_pass = request.POST.get('new_password')
        if new_pass and new_pass.strip():
            user_obj.set_password(new_pass)
            messages.warning(request, f"تم تغيير كلمة المرور.")
            
        user_obj.save()
        messages.success(request, "تم تحديث المستخدم ✅")
        return redirect('super_users_list')
        
    countries = Country.objects.filter(is_active=True)
    return render(request, 'supervisor/user_edit.html', {'user_obj': user_obj, 'countries': countries})

@login_required
def user_delete(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_to_delete = get_object_or_404(filter_by_country(request.user, User.objects.all()), id=user_id)
    try:
        user_to_delete.delete()
        messages.success(request, "تم حذف العميل بنجاح ✅")
    except ProtectedError:
        user_to_delete.is_active = False
        user_to_delete.is_banned = True 
        user_to_delete.save()
        send_push_to_user(user_to_delete, "حظر الحساب 🚫", "تم إيقاف حسابك من قبل الإدارة.")
        messages.warning(request, f"⚠️ لا يمكن الحذف النهائي لوجود فواتير. تم الحظر والتعطيل.")
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def banned_users(request):
    if not is_supervisor(request.user): return redirect('home')
    users = filter_by_country(request.user, User.objects.filter(is_banned=True))
    return render(request, 'supervisor/banned_users.html', {'users': users})

@login_required
def ban_user(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user = get_object_or_404(filter_by_country(request.user, User.objects.all()), pk=user_id)
    action = request.GET.get('action')
    if action == 'ban':
        user.is_banned = True
        send_push_to_user(user, "حظر الحساب 🚫", "تم حظر حسابك لمخالفة الشروط.")
        messages.warning(request, f"تم حظر {user.username}")
    elif action == 'unban':
        user.is_banned = False
        send_notification(user, "فك الحظر ✅", "تمت مراجعة حسابك وفك الحظر، يمكنك استخدام المنصة الآن.")
        send_push_to_user(user, "حسابك متاح الآن ✅", "تم فك الحظر عن حسابك، نورتنا من تاني.")
        messages.success(request, f"تم فك حظر {user.username}")
    user.save()
    return redirect(request.META.get('HTTP_REFERER', 'super_users_list'))

@login_required
def customers_analytics(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    range_type = request.GET.get('range', 'month')
    custom_start, custom_end = request.GET.get('start'), request.GET.get('end')
    today = timezone.now().date()
    start_date = today.replace(day=1)
    
    if range_type == 'today': start_date = today
    elif range_type == 'week': start_date = today - timedelta(days=7)
    elif range_type == 'year': start_date = today.replace(month=1, day=1)
    elif range_type == 'custom' and custom_start:
        try: start_date = parse_date(custom_start)
        except: pass

    base_users = filter_by_country(request.user, User.objects.filter(role='CUSTOMER'))
    new_customers_count = base_users.filter(date_joined__date__gte=start_date).count()
    top_customers = base_users.annotate(
        total_spent=Sum('orders__final_total', filter=Q(orders__status='DELIVERED')),
        orders_count=Count('orders', filter=Q(orders__status='DELIVERED'))
    ).order_by('-total_spent')[:10]

    return render(request, 'supervisor/customers_analytics.html', {
        'new_customers_count': new_customers_count, 'top_customers': top_customers,
        'current_range': range_type, 'start_date': start_date,
    })

@login_required
def customer_profile_admin(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    customer = get_object_or_404(filter_by_country(request.user, User.objects.all()), pk=user_id)
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    total_spent = orders.filter(status='DELIVERED').aggregate(Sum('final_total'))['final_total__sum'] or 0
    return render(request, 'supervisor/customer_profile.html', {'customer': customer, 'orders': orders, 'total_spent': total_spent})


# ==========================================
# 8. الإدارة المالية والمحافظ (Finance & Wallets)
# ==========================================
@login_required
def pending_deposits(request):
    if not is_supervisor(request.user): return redirect('home')
    deposits = filter_by_country(request.user, DepositRequest.objects.filter(status=DepositRequest.Status.PENDING)).order_by('-created_at')
    return render(request, 'supervisor/pending_deposits.html', {'deposits': deposits})

@login_required
def approve_deposit(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    deposit = get_object_or_404(filter_by_country(request.user, DepositRequest.objects.all()), pk=pk)
    deposit.status = DepositRequest.Status.APPROVED
    deposit.save()
    link = get_url_safely('merchant_wallet', '/merchant/wallet/')
    send_notification(deposit.merchant.user, "تم قبول الإيداع 💰", "تم مراجعة وقبول طلب الإيداع الخاص بك.", link)
    send_push_to_user(deposit.merchant.user, "قبول إيداع 💰", "تمت الموافقة على طلب إيداعك وإضافته لمحفظتك.")
    messages.success(request, "تم قبول الإيداع.")
    return redirect('super_pending_deposits')

@login_required
def pending_withdrawals(request):
    if not is_supervisor(request.user): return redirect('home')
    withdrawals = filter_by_country(request.user, WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING)).order_by('-created_at')
    return render(request, 'supervisor/pending_withdrawals.html', {'withdrawals': withdrawals})

@login_required
def approve_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    withdrawal = get_object_or_404(filter_by_country(request.user, WithdrawalRequest.objects.all()), pk=pk)
    
    if withdrawal.status == 'PENDING':
        with transaction.atomic():
            withdrawal.status = 'APPROVED'
            withdrawal.save()
            
            # 🔥 تحديث وصف المعاملة المالية في سجل التاجر لكي يظهر "تم التحويل"
            tx = WalletTransaction.objects.filter(
                wallet=withdrawal.merchant.wallet,
                transaction_type='WITHDRAWAL',
                description__contains=f"#{withdrawal.id}"
            ).first()
            
            if tx:
                tx.description = f"سحب أرباح (طلب #{withdrawal.id}) - ✅ تم التحويل بنجاح"
                tx.save()

        # إرسال الإشعارات
        link = get_url_safely('merchant_wallet', '/merchant/wallet/')
        send_notification(withdrawal.merchant.user, "تم تحويل الأرباح 💸", f"تمت الموافقة على سحب {withdrawal.amount} ج.م عبر {withdrawal.get_withdrawal_method_display()} وتم التحويل.", link)
        send_push_to_user(withdrawal.merchant.user, "تحويل أرباح 💸", f"تم تحويل مبلغ {withdrawal.amount} ج.م بنجاح.")
        messages.success(request, f"تم تأكيد التحويل بنجاح ✅")
        
    return redirect('super_pending_withdrawals')

@login_required
def reject_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    req = get_object_or_404(filter_by_country(request.user, WithdrawalRequest.objects.all()), pk=pk)
    
    if req.status == 'PENDING':
        with transaction.atomic():
            req.status = 'REJECTED'
            req.save()
            
            # 1. إرجاع المبلغ لمحفظة التاجر
            wallet = Wallet.objects.select_for_update().get(id=req.merchant.wallet.id)
            wallet.balance += req.amount
            wallet.save()
            
            # 2. تحديث وصف معاملة السحب القديمة لبيان الرفض
            old_tx = WalletTransaction.objects.filter(wallet=wallet, transaction_type='WITHDRAWAL', description__contains=f"#{req.id}").first()
            if old_tx:
                old_tx.description = f"سحب أرباح (طلب #{req.id}) - ❌ تم الرفض"
                old_tx.save()

            # 3. تسجيل معاملة استرداد جديدة
            WalletTransaction.objects.create(
                wallet=wallet, amount=req.amount, transaction_type='COMPENSATION',
                description=f"استرداد رصيد لرفض طلب سحب #{req.id}", 
                balance_after=wallet.balance, is_released=True
            )
            
        send_notification(req.merchant.user, "رفض طلب السحب ❌", f"تم رفض طلب سحب {req.amount} ج.م وإعادة المبلغ لمحفظتك.")
        messages.warning(request, f"تم رفض السحب وإعادة المبلغ للتاجر.")
        
    return redirect('super_pending_withdrawals')

@login_required
def wallets_list(request):
    if not is_supervisor(request.user): return redirect('home')
    for m in filter_by_country(request.user, MerchantProfile.objects.all()): 
        Wallet.objects.get_or_create(merchant=m)
    wallets = filter_by_country(request.user, Wallet.objects.all()).order_by('-balance')
    return render(request, 'supervisor/wallets_list.html', {'wallets': wallets})

@login_required
def adjust_wallet(request, wallet_id):
    if not is_supervisor(request.user): return redirect('home')
    wallet_obj = get_object_or_404(filter_by_country(request.user, Wallet.objects.all()), pk=wallet_id)
    if request.method == 'POST':
        amount = parse_decimal(request.POST.get('amount'))
        reason = request.POST.get('reason')
        action = request.POST.get('action') 
        
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=wallet_obj.pk)
            if action == 'add':
                wallet.balance += amount
                desc, msg = f"إضافة إدارية: {reason}", f"تم إضافة {amount} إدارياً لمحفظتك. السبب: {reason}"
            else:
                wallet.balance -= amount
                desc, msg = f"خصم إداري: {reason}", f"تم خصم {amount} إدارياً من محفظتك. السبب: {reason}"
            
            wallet.save()
            WalletTransaction.objects.create(wallet=wallet, amount=amount if action=='add' else -amount, transaction_type=WalletTransaction.TxType.COMPENSATION, description=desc, balance_after=wallet.balance, is_released=True)
            
            link = get_url_safely('merchant_wallet', '/merchant/wallet/')
            send_notification(wallet.merchant.user, "تحديث رصيد المحفظة 💰", msg, link)
            messages.success(request, "تم تعديل الرصيد بنجاح.")
            return redirect('super_wallets_list')
    return render(request, 'supervisor/adjust_wallet.html', {'wallet': wallet_obj})

@login_required
def finance_overview(request):
    if not is_supervisor(request.user): return redirect('home')
    range_type = request.GET.get('range', 'month') 
    custom_start, custom_end = request.GET.get('start'), request.GET.get('end')
    today = timezone.now().date()
    start_date, end_date = today.replace(day=1), today

    if range_type == 'today': start_date = today
    elif range_type == 'week': start_date = today - timedelta(days=7)
    elif range_type == 'year': start_date = today.replace(month=1, day=1)
    elif range_type == 'custom' and custom_start and custom_end:
        try: start_date, end_date = parse_date(custom_start), parse_date(custom_end)
        except: pass 

    base_qs = filter_by_country(request.user, WalletTransaction.objects.filter(created_at__date__range=[start_date, end_date]))
    
    income_val = base_qs.filter(amount__lt=0, description__contains="خصم عمولة").aggregate(Sum('amount'))['amount__sum'] or 0
    income = abs(float(income_val))
    expenses = float(base_qs.filter(transaction_type=WalletTransaction.TxType.COMPENSATION).aggregate(Sum('amount'))['amount__sum'] or 0)
    net_profit = income - expenses
    total_merchants_balance = float(filter_by_country(request.user, Wallet.objects.all()).aggregate(Sum('balance'))['balance__sum'] or 0)

    trunc_func = TruncMonth if range_type == 'year' else TruncDay
    date_format = "%b %Y" if range_type == 'year' else "%d %b"

    chart_qs = base_qs.filter(amount__lt=0, description__contains="خصم عمولة").annotate(period=trunc_func('created_at')).values('period').annotate(total=Sum('amount')).order_by('period')
    labels, values = [], []
    for item in chart_qs:
        labels.append(item['period'].strftime(date_format))
        values.append(abs(float(item['total'])))

    if not labels: labels, values = ["لا توجد بيانات"], [0]

    return render(request, 'supervisor/finance_overview.html', {
        'income': income, 'expenses': expenses, 'net_profit': net_profit,
        'total_merchants_balance': total_merchants_balance, 'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values), 'current_range': range_type, 'start_date': start_date, 'end_date': end_date,
    })

@login_required
def finance_logs(request):
    """سجل المعاملات المالية الشامل للإدارة مع الفلاتر المتقدمة"""
    if not is_supervisor(request.user): 
        return redirect('home')
        
    # استقبال الفلاتر من الرابط
    tx_type = request.GET.get('type')
    search_query = request.GET.get('q', '').strip()
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # جلب السجلات الخاصة بدولة المشرف
    logs = filter_by_country(request.user, WalletTransaction.objects.all()).select_related('wallet__merchant__user').order_by('-created_at')

    # 1. فلترة بنوع العملية
    if tx_type: 
        logs = logs.filter(transaction_type=tx_type)
        
    # 2. بحث متقدم (في الوصف، اسم التاجر، أو رقم الطلب المرتبط)
    if search_query:
        logs = logs.filter(
            Q(description__icontains=search_query) | 
            Q(wallet__merchant__user__first_name__icontains=search_query) |
            Q(wallet__merchant__user__last_name__icontains=search_query) |
            Q(related_order_id__icontains=search_query)
        )
        
    # 3. فلترة بالتاريخ
    if start_date and end_date:
        try:
            from django.utils.dateparse import parse_date
            logs = logs.filter(created_at__date__range=[parse_date(start_date), parse_date(end_date)])
        except:
            pass # تجاهل الخطأ لو التاريخ غير صالح

    context = {
        'logs': logs,
        'tx_types': WalletTransaction.TxType.choices,
        'current_type': tx_type,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'supervisor/finance_logs.html', context)

@login_required
def export_profit_report(request):
    if not is_supervisor(request.user): return redirect('home')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="profits_report.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['المعرف', 'التاجر', 'النوع', 'المبلغ', 'الوصف', 'التاريخ'])
    transactions = filter_by_country(request.user, WalletTransaction.objects.all()).order_by('-created_at')
    for tx in transactions:
        writer.writerow([tx.id, tx.wallet.merchant.user.first_name, tx.get_transaction_type_display(), tx.amount, tx.description, tx.created_at.strftime("%Y-%m-%d %H:%M")])
    return response

@login_required
def export_debts_report(request):
    if not is_supervisor(request.user): return redirect('home')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="merchants_balances.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['التاجر', 'رقم الهاتف', 'الرصيد المتاح', 'الرصيد المعلق'])
    wallets = filter_by_country(request.user, Wallet.objects.all())
    for w in wallets:
        writer.writerow([w.merchant.user.first_name, w.merchant.user.phone_primary, w.balance, w.pending_balance])
    return response


# ==========================================
# 9. الإعدادات، العروض، الشروط والأقسام (مع الترجمة المدمجة)
# ==========================================
@login_required
def site_settings_view(request):
    if not is_supervisor(request.user): return redirect('home')
    if str(request.user.role) != 'OWNER' and not request.user.country:
        messages.error(request, "أنت غير مربوط بدولة معينة لضبط إعداداتها.")
        return redirect('home')
        
    current_country = request.user.country if str(request.user.role) != 'OWNER' else None
    settings_obj = SiteSetting.get_settings(current_country)
    
    if request.method == 'POST':
        try:
            settings_obj.site_name = request.POST.get('site_name') or "Elbazaar"
            settings_obj.platform_fee_fixed = parse_decimal(request.POST.get('fee_fixed'))
            settings_obj.platform_fee_percentage = parse_decimal(request.POST.get('fee_percent'))
            settings_obj.min_withdrawal_amount = parse_decimal(request.POST.get('min_withdrawal'))
            settings_obj.min_wallet_balance = parse_decimal(request.POST.get('reserved_balance'))
            settings_obj.min_active_balance = parse_decimal(request.POST.get('min_active'))
            settings_obj.referral_reward_percentage = parse_decimal(request.POST.get('ref_reward_percent') or 10.00)
            settings_obj.referral_reward_validity_days = int(request.POST.get('ref_validity_days') or 30)
            
            # 🔥 الحقول الجديدة الخاصة بعمولات بوابة فواتيرك
            settings_obj.fawaterk_fee_percentage = parse_decimal(request.POST.get('fawaterk_fee_percent') or '2.00')
            settings_obj.fawaterk_fee_fixed = parse_decimal(request.POST.get('fawaterk_fee_fixed') or '2.00')
            
            settings_obj.pending_balance_release_hours = int(request.POST.get('release_hours') or 24)
            settings_obj.referral_grace_period_hours = int(request.POST.get('ref_grace') or 24)
            settings_obj.referral_discount_limit_pct = int(request.POST.get('ref_limit') or 10)
            settings_obj.referral_reward_limit_orders = int(request.POST.get('ref_orders_limit') or 1)

            # 🔥 الحقول المالية القصوى (الجديدة) لنظام الإحالة
            settings_obj.referral_discount_max_amount = parse_decimal(request.POST.get('ref_discount_max_amount') or 100.00)
            settings_obj.referral_reward_max_amount = parse_decimal(request.POST.get('ref_reward_max_amount') or 100.00)

            gateway = request.POST.get('active_payment_gateway')
            if gateway in ['PAYMOB', 'FAWATERK']:
                settings_obj.active_payment_gateway = gateway

            if request.FILES.get('banner'):
                settings_obj.banner_image = request.FILES.get('banner')
                  
            settings_obj.save()
            notify_admins(title="تحديث الإعدادات ⚙️", message=f"قام {request.user.first_name} بتحديث إعدادات النظام.")
            messages.success(request, "تم حفظ الإعدادات بنجاح ✅")
        except Exception as e:
            messages.error(request, f"🚨 خطأ في البيانات: يرجى التأكد من إدخال أرقام صحيحة.")
        return redirect('super_site_settings')
          
    return render(request, 'supervisor/site_settings.html', {'settings': settings_obj})

@login_required
def manage_categories(request):
    if not is_supervisor(request.user): return redirect('home')
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            cat = Category.objects.create(name=request.POST.get('name'), image=request.FILES.get('image'))
            save_dynamic_translations(request, cat, ['name']) # حفظ الترجمات آلياً
            cat.save()
            messages.success(request, "تمت إضافة القسم بنجاح ✅")
                
        elif action == 'edit':
            cat_id = request.POST.get('category_id')
            cat = get_object_or_404(Category, id=cat_id)
            cat.name = request.POST.get('name')
            if request.FILES.get('image'): cat.image = request.FILES.get('image')
            save_dynamic_translations(request, cat, ['name']) # تحديث الترجمات آلياً
            cat.save()
            messages.success(request, "تم تعديل القسم بنجاح ✅")
            
        elif action == 'delete':
            cat_id = request.POST.get('category_id')
            Category.objects.filter(pk=cat_id).delete()
            messages.success(request, "تم حذف القسم بنجاح 🗑️")
            
        return redirect('super_categories')
        
    return render(request, 'supervisor/categories.html', {'categories': Category.objects.all()})

@login_required
def edit_category(request, pk):
    return redirect('super_categories')

@login_required
def delete_category(request, pk):
    return redirect('super_categories')

@login_required
def manage_offers(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    offers = filter_by_country(request.user, Offer.objects.filter(is_platform_offer=True)).order_by('-created_at')
    return render(request, 'supervisor/manage_offers.html', {'offers': offers})

@login_required
def create_platform_offer(request):
    if not is_supervisor(request.user): return redirect('home')
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        percentage = int(request.POST.get('percentage') or 0)
        days = int(request.POST.get('days'))
        free_shipping = request.POST.get('free_shipping') == 'on'
        threshold = int(request.POST.get('threshold', 1))
        
        product = get_object_or_404(filter_by_country(request.user, Product.objects.all()), pk=product_id)
        Offer.objects.update_or_create(
            product=product,
            defaults={
                'discount_percentage': percentage, 'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=days),
                'is_active': True, 'is_platform_offer': True,
                'free_shipping': free_shipping, 'free_shipping_threshold': threshold
            }
        )
        link = get_url_safely('merchant_products', '/merchant/products/')
        send_notification(product.merchant.user, "عرض منصة جديد! 🏷️", f"قامت المنصة بتفعيل عرض {percentage}% على منتج '{product.name}'.", link)
        send_push_to_user(product.merchant.user, "عرض مميز لمنتجك! 🏷️", f"إدارة المنصة أضافت عرض بخصم {percentage}% على '{product.name}'.")
        messages.success(request, "تم إطلاق عرض المنصة!")
        return redirect('supervisor_dashboard')
        
    products = filter_by_country(request.user, Product.objects.filter(is_active=True))
    return render(request, 'supervisor/create_offer.html', {'products': products})

@login_required
def delete_offer_admin(request, pk):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    offer = get_object_or_404(filter_by_country(request.user, Offer.objects.all()), pk=pk)
    offer.delete()
    messages.success(request, "تم حذف العرض.")
    return redirect('super_manage_offers')

@login_required
def manage_banners(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    if request.method == 'POST':
        c = request.user.country if str(request.user.role) != 'OWNER' else None
        Banner.objects.create(country=c, image=request.FILES.get('image'), link=request.POST.get('link'), expires_at=request.POST.get('expires_at') or None)
        messages.success(request, "تم إضافة البانر بنجاح.")
        return redirect('super_manage_banners')
    banners = filter_by_country(request.user, Banner.objects.all()).order_by('-created_at')
    return render(request, 'supervisor/manage_banners.html', {'banners': banners})

@login_required
def delete_banner(request, pk):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    banner = get_object_or_404(filter_by_country(request.user, Banner.objects.all()), pk=pk)
    banner.delete()
    messages.success(request, "تم الحذف.")
    return redirect('super_manage_banners')

@login_required
def manage_terms(request):
    if not is_supervisor(request.user): return redirect('home')
    is_owner = str(request.user.role) == 'OWNER' or request.user.is_superuser
        
    if request.method == 'POST':
        action = request.POST.get('action') 
        c = Country.objects.get(id=request.POST.get('country_id')) if is_owner and request.POST.get('country_id') else (None if is_owner else request.user.country)
        
        if action == 'add':
            term = TermsAndCondition.objects.create(
                country=c, title=request.POST.get('title'), content=request.POST.get('content'),
                order=request.POST.get('order', 1), document_type=request.POST.get('document_type'),
                user_type=request.POST.get('user_type')
            )
            save_dynamic_translations(request, term, ['title', 'content'])
            term.save()
            messages.success(request, "تمت إضافة البند بنجاح ✅")
            
        elif action == 'edit':
            term = get_object_or_404(filter_by_country(request.user, TermsAndCondition.objects.all()), id=request.POST.get('term_id'))
            term.title, term.content, term.order = request.POST.get('title'), request.POST.get('content'), request.POST.get('order', 1)
            term.document_type, term.user_type = request.POST.get('document_type'), request.POST.get('user_type')
            term.is_active = request.POST.get('is_active') == 'on' 
            if is_owner: term.country = c
            
            save_dynamic_translations(request, term, ['title', 'content'])
            term.save()
            messages.success(request, "تم تحديث البند بنجاح ✏️")
            
        elif action == 'delete':
            term = get_object_or_404(filter_by_country(request.user, TermsAndCondition.objects.all()), id=request.POST.get('term_id'))
            term.delete()
            messages.success(request, "تم حذف البند بنجاح 🗑️")
            
        return redirect('super_manage_terms')

    terms = filter_by_country(request.user, TermsAndCondition.objects.all()).order_by('document_type', 'user_type', 'order')
    countries = Country.objects.filter(is_active=True) if is_owner else None
    return render(request, 'supervisor/manage_terms.html', {'terms': terms, 'countries': countries, 'is_owner': is_owner})

@login_required
def edit_term(request, pk):
    return redirect('super_manage_terms')

@login_required
def delete_term(request, pk):
    return redirect('super_manage_terms')

@login_required
def edit_about_us(request):
    if not is_supervisor(request.user): return redirect('home')
    c = request.user.country if str(request.user.role) != 'OWNER' else None
    about, _ = AboutUs.objects.get_or_create(country=c)
    
    if request.method == 'POST':
        about.content = request.POST.get('content')
        save_dynamic_translations(request, about, ['content'])
        about.save()
        messages.success(request, "تم تحديث صفحة 'من نحن' بنجاح ✅")
        return redirect('super_edit_about_us')
        
    return render(request, 'supervisor/edit_about_us.html', {'about': about})

@login_required
def manage_vouchers(request):
    if not is_supervisor(request.user): return redirect('home')
    if request.method == 'POST':
        code = request.POST.get('code')
        if PersonalVoucher.objects.filter(code=code).exists():
            messages.error(request, "كود الخصم هذا موجود مسبقاً.")
        else:
            customer = get_object_or_404(filter_by_country(request.user, User.objects.all()), id=request.POST.get('customer_id'))
            PersonalVoucher.objects.create(
                customer=customer, title=request.POST.get('title'), code=code.upper(),
                discount_percentage=int(parse_decimal(request.POST.get('discount_percentage', 0))),
                max_discount_amount=parse_decimal(request.POST.get('max_discount_amount', 0)),
                remaining_items=int(parse_decimal(request.POST.get('remaining_items', 1))),
                free_shipping=request.POST.get('free_shipping') == 'on',
                expires_at=request.POST.get('expires_at')
            )
            link = get_url_safely('cart_view', '/cart/')
            send_notification(customer, "هدية خاصة لك! 🎁", f"لقد حصلت على قسيمة خصم: {code}. الاستمتاع بالتسوق!", link)
            send_push_to_user(customer, "كوبون خصم هدية! 🎁", f"استخدم الكوبون ({code}) واستمتع بخصم على مشترياتك.")
            messages.success(request, f"تم إرسال العرض بنجاح للعميل {customer.first_name} ✅")
            return redirect('super_manage_vouchers')

    customers = filter_by_country(request.user, User.objects.filter(is_superuser=False)).order_by('-date_joined')
    vouchers = filter_by_country(request.user, PersonalVoucher.objects.all()).order_by('-created_at')
    return render(request, 'supervisor/manage_vouchers.html', {'customers': customers, 'vouchers': vouchers, 'suggested_code': get_random_string(length=8).upper()})

@login_required
def delete_voucher(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    voucher = get_object_or_404(filter_by_country(request.user, PersonalVoucher.objects.all()), pk=pk)
    voucher.delete()
    messages.success(request, "تم حذف القسيمة بنجاح.")
    return redirect('super_manage_vouchers')


# ==========================================
# 🔥 10. فريق العمل وإدارة الأدوار
# ==========================================
AVAILABLE_PERMISSIONS = [
    ('orders', 'إدارة الطلبات'), ('products', 'إدارة المنتجات'), ('categories', 'إدارة الأقسام'),
    ('users', 'إدارة المستخدمين'), ('merchants', 'تفعيل التجار'), ('finance', 'المالية والسحوبات'),
    ('settings', 'إعدادات الموقع'), ('support', 'الدعم الفني'), ('team', 'فريق العمل'),
    ('offers', 'إدارة العروض'), ('notifications', 'إرسال إشعارات'), ('banners', 'إدارة البانرات الإعلانية'),
]

@login_required
def team_management(request):
    if not (request.user.is_superuser or str(request.user.role) in ['OWNER', 'COUNTRY_ADMIN']): 
        return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        username, phone, email, password = request.POST.get('username'), request.POST.get('phone'), request.POST.get('email'), request.POST.get('password')
        
        if User.objects.filter(username=username).exists(): 
            messages.error(request, "الاسم موجود مسبقاً.")
        elif User.objects.filter(phone_primary=phone).exists(): 
            messages.error(request, "الهاتف مسجل بالفعل.")
        else:
            try:
                new_admin = User.objects.create_user(username=username, email=email, password=password, phone_primary=phone)
                new_admin.is_staff = True 
                
                if str(request.user.role) == 'OWNER':
                    country_id, base_role = request.POST.get('country_id'), request.POST.get('base_role')
                    if country_id: new_admin.country = Country.objects.get(id=country_id)
                    new_admin.role = base_role if base_role else User.Role.ADMIN_LVL3
                else:
                    new_admin.country = request.user.country
                    new_admin.role = User.Role.ADMIN_LVL3
                    
                role_id = request.POST.get('custom_role')
                if role_id: new_admin.custom_role = CustomRole.objects.get(id=role_id)
                new_admin.save()
                
                link = get_url_safely('super_team', '/super/team/')
                notify_admins(title="إضافة مشرف جديد 🛡️", message=f"قام {request.user.first_name} بتعيين مشرف جديد بالنظام.", link=link)
                
                messages.success(request, f"تم تعيين المشرف {username} بنجاح ✅")
            except Exception as e: 
                messages.error(request, f"حدث خطأ: {e}")
                
        return redirect('super_team')
        
    team = filter_by_country(request.user, User.objects.filter(role__in=[User.Role.COUNTRY_ADMIN, User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3])).exclude(pk=request.user.pk)
    countries = Country.objects.filter(is_active=True) if str(request.user.role) == 'OWNER' else None
    custom_roles = filter_by_country(request.user, CustomRole.objects.all())
    
    return render(request, 'supervisor/team_management.html', {'team': team, 'custom_roles': custom_roles, 'countries': countries})


@login_required
def manage_roles(request):
    if not (request.user.is_superuser or str(request.user.role) in ['OWNER', 'COUNTRY_ADMIN']): 
        return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        c = request.user.country if str(request.user.role) != 'OWNER' else None
        CustomRole.objects.create(country=c, name=request.POST.get('name'), permissions=",".join(request.POST.getlist('permissions')))
        messages.success(request, "تم إنشاء الدور بنجاح.")
        return redirect('super_manage_roles')
        
    roles = filter_by_country(request.user, CustomRole.objects.all())
    return render(request, 'supervisor/manage_roles.html', {'roles': roles, 'available_perms': AVAILABLE_PERMISSIONS})

@login_required
def delete_role(request, pk):
    if not (request.user.is_superuser or str(request.user.role) in ['OWNER', 'COUNTRY_ADMIN']): return redirect('home')
    role = get_object_or_404(filter_by_country(request.user, CustomRole.objects.all()), pk=pk)
    role.delete()
    messages.success(request, "تم حذف الدور.")
    return redirect('super_manage_roles')


# ==========================================
# 11. الدعم الفني، الشكاوى وتسوية المرتجعات
# ==========================================
@login_required
def send_broadcast(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        title, message, target = request.POST.get('title'), request.POST.get('message'), request.POST.get('target')
        link, specific_user_id = request.POST.get('link') or None, request.POST.get('specific_user_id') 
        
        if target == 'SPECIFIC' and specific_user_id:
            try:
                user = filter_by_country(request.user, User.objects.all()).get(id=specific_user_id)
                send_notification(user, title, message, link)
                send_push_to_user(user, title, message)
                messages.success(request, f"تم إرسال الإشعار للمستخدم '{user.first_name}' بنجاح ✅")
            except User.DoesNotExist:
                messages.error(request, "لم يتم العثور على المستخدم المحدد (أو لا ينتمي لدولتك).")
                
        else:
            users = filter_by_country(request.user, User.objects.filter(is_active=True))
            if target == 'MERCHANTS': users = users.filter(role='MERCHANT')
            elif target == 'CUSTOMERS': users = users.filter(role='CUSTOMER')
            
            Notification.objects.bulk_create([Notification(recipient=u, title=title, message=message, link=link) for u in users])
            for u in users: send_push_to_user(u, title, message)
            messages.success(request, f"تم إرسال الإشعار لـ {users.count()} مستخدم بنجاح ✅")
            
        return redirect('supervisor_dashboard')
        
    all_users = filter_by_country(request.user, User.objects.filter(is_superuser=False)).order_by('-date_joined')
    return render(request, 'supervisor/send_broadcast.html', {'all_users': all_users})

@login_required
def support_tickets(request):
    if not is_supervisor(request.user): return redirect('home')
    status = request.GET.get('status')
    tickets = filter_by_country(request.user, SupportTicket.objects.all()).order_by('-created_at')
    if status: tickets = tickets.filter(status=status)
    return render(request, 'supervisor/support_tickets.html', {'tickets': tickets})

@login_required
def support_ticket_detail(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    ticket = get_object_or_404(filter_by_country(request.user, SupportTicket.objects.all()), pk=pk)
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            TicketMessage.objects.create(ticket=ticket, sender=request.user, message=message, is_support_reply=True)
            ticket.status = 'IN_PROGRESS' 
            ticket.save()
            # Customer doesn't have a guaranteed reliable URL string unless using reverse
            link = get_url_safely('my_tickets', '#')
            send_notification(ticket.customer, "رد جديد من الدعم 📩", f"تم الرد على تذكرتك رقم #{ticket.id}. اضغط للمشاهدة.", link)
            send_push_to_user(ticket.customer, "رد الدعم الفني 📩", f"فريق الدعم رد على تذكرتك.")
            messages.success(request, "تم إرسال الرد.")
            
        if request.POST.get('status'):
            ticket.status = request.POST.get('status')
            ticket.save()
            messages.info(request, "تم تحديث الحالة.")
            
        return redirect('super_ticket_detail', pk=pk)
        
    return render(request, 'supervisor/support_ticket_detail.html', {'ticket': ticket})

@login_required
def admin_complaints_list(request):
    if not is_supervisor(request.user): return redirect('home')
    complaints = filter_by_country(request.user, DeliveryComplaint.objects.all()).order_by('-created_at')
    return render(request, 'supervisor/admin_complaints_list.html', {'complaints': complaints})


# ==========================================
# دوال استرجاع الأموال (Refund Logic)
# ==========================================
def process_paymob_refund(transaction_id, amount):
    try:
        auth_response = requests.post("https://accept.paymob.com/api/auth/tokens", json={"api_key": settings.PAYMOB_API_KEY})
        if auth_response.status_code != 201: return False, "فشل تسجيل الدخول لـ Paymob."
        refund_response = requests.post("https://accept.paymob.com/api/acceptance/void_refund/refund", json={
            "auth_token": auth_response.json().get('token'), "transaction_id": str(transaction_id), "amount_cents": int(float(amount) * 100)
        })
        if refund_response.status_code in [200, 201]: return True, "تم الإرجاع بنجاح ✅"
        return False, f"Paymob Error: {refund_response.json().get('detail', 'مرفوض')}"
    except Exception as e: return False, f"خطأ اتصال: {str(e)}"

def process_fawaterk_refund(invoice_id, amount):
    """دالة استرداد الأموال عبر فواتيرك آلياً"""
    try:
        headers = {
            'Authorization': f'Bearer {settings.FAWATERK_API_KEY}',
            'Content-Type': 'application/json'
        }
        data = {
            "invoice_id": invoice_id,
            "refund_amount": float(amount)
        }
        url = "https://staging.fawaterk.com/api/v2/refund"
        resp = requests.post(url, json=data, headers=headers)
        if resp.status_code in [200, 201]: 
            return True, "تم الإرجاع عبر فواتيرك بنجاح ✅"
        return False, f"Fawaterk Error: {resp.json().get('message', 'مرفوض')}"
    except Exception as e: 
        return False, f"خطأ اتصال: {str(e)}"


@login_required
def admin_resolve_complaint(request, complaint_id):
    if not is_supervisor(request.user): return redirect('home')
    complaint = get_object_or_404(filter_by_country(request.user, DeliveryComplaint.objects.all()), id=complaint_id)
    order, merchant_wallet = complaint.order, complaint.order.merchant.wallet

    if request.method == 'POST':
        resolution_action = request.POST.get('resolution_action', 'refund')
        admin_notes = request.POST.get('admin_notes', '')

        with transaction.atomic():
            if resolution_action == 'refund':
                old_transactions = WalletTransaction.objects.filter(wallet=merchant_wallet, related_order_id=order.order_id, transaction_type__in=['PENDING', 'COMPENSATION', 'SALE'])
                if old_transactions.exists():
                    for old_tx in old_transactions:
                        if not old_tx.is_released: merchant_wallet.pending_balance -= old_tx.amount
                        else: merchant_wallet.balance -= old_tx.amount
                        WalletTransaction.objects.create(wallet=merchant_wallet, amount=-old_tx.amount, transaction_type='REFUND', related_order_id=order.order_id, description=f"تسوية مرتجع #{order.order_id}", balance_after=merchant_wallet.balance, is_released=old_tx.is_released)
                    merchant_wallet.save()

                shipping_to_deduct = Decimal(order.shipping_cost)
                if shipping_to_deduct == 0 and not order.is_first_order:
                    rate_obj = MerchantShippingRate.objects.filter(merchant=order.merchant, governorate=order.governorate).first()
                    shipping_to_deduct = (rate_obj.rate if rate_obj else Decimal(50)) + sum(i.product_size.product.shipping_fee * i.quantity for i in order.items.all())

                deserves_compensation = order.payment_method in ['ONLINE', 'WALLET'] or order.is_first_order
                if shipping_to_deduct > 0 and deserves_compensation:
                    merchant_wallet.balance += shipping_to_deduct 
                    WalletTransaction.objects.create(wallet=merchant_wallet, amount=shipping_to_deduct, transaction_type='COMPENSATION', related_order_id=order.order_id, description=f"تعويض شحن #{order.order_id}", balance_after=merchant_wallet.balance, is_released=True)
                    merchant_wallet.save()

                if order.payment_method in ['ONLINE', 'WALLET']:
                    platform_fees_to_deduct = parse_decimal(order.platform_fees)
                    refund_to_customer = max(Decimal(0), parse_decimal(order.final_total) - shipping_to_deduct - platform_fees_to_deduct)
                    
                    if refund_to_customer > 0:
                        is_success = False
                        paymob_msg = ""
                        gateway_used = getattr(order, 'payment_gateway_used', 'PAYMOB')
                        
                        if gateway_used == 'FAWATERK' and getattr(order, 'gateway_order_id', None):
                            is_success, paymob_msg = process_fawaterk_refund(order.gateway_order_id, refund_to_customer)
                        elif gateway_used == 'PAYMOB' and (getattr(order, 'paymob_transaction_id', None) or getattr(order, 'gateway_transaction_id', None)):
                            tx_id = getattr(order, 'gateway_transaction_id', getattr(order, 'paymob_transaction_id', None))
                            is_success, paymob_msg = process_paymob_refund(tx_id, refund_to_customer)
                        
                        if is_success: 
                            messages.success(request, f"تم التسوية وإرجاع {refund_to_customer} للعميل.")
                        else: 
                            messages.error(request, f"فشل الإرجاع الآلي: {paymob_msg}")
                
                order.status = 'RETURNED'
                order.save()
                complaint.is_resolved = True
                complaint.admin_notes = admin_notes or 'تمت التسوية المالية كمرتجع.'
                complaint.save()
                
                link = get_url_safely('my_orders', '#')
                send_notification(order.customer, "تسوية شكوى ⚖️", f"تمت تسوية شكواك المتعلقة بالطلب #{order.order_id} وإرجاع المبلغ.", link)
                send_push_to_user(order.customer, "تسوية شكوى ⚖️", f"تمت تسوية شكواك المتعلقة بالطلب #{order.order_id} وإرجاع المبلغ.")
                
            elif resolution_action == 'force_deliver':
                order.status, order.is_confirmed_by_customer, order.rejection_reason = 'DELIVERED', True, None
                order.save()

                from store.services import OrderService
                OrderService.apply_merchant_cashback(order) #  تفعيل الكاش باك بالقوة

                complaint.is_resolved, complaint.admin_notes = True, admin_notes or 'تأكيد التسليم لصالح التاجر.'
                complaint.save()
                
                link = get_url_safely('my_orders', '#')
                send_notification(order.customer, "تحديث الشكوى ⚠️", f"تم إغلاق الشكوى للطلب #{order.order_id} وتأكيد التسليم.", link)
                send_push_to_user(order.customer, "تحديث الشكوى ⚠️", f"تم إغلاق الشكوى للطلب #{order.order_id} وتأكيد التسليم.")
                messages.success(request, "تم إغلاق الشكوى وتأكيد التسليم بالقوة!")

    return redirect(request.META.get('HTTP_REFERER', 'admin_complaints_list'))

@login_required
def super_reviews_list(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    reviews = filter_by_country(request.user, ProductReview.objects.all()).order_by('-created_at')
    q, merchant_id, rating = request.GET.get('q'), request.GET.get('merchant'), request.GET.get('rating')
    if q: reviews = reviews.filter(Q(product__name__icontains=q) | Q(user__first_name__icontains=q) | Q(comment__icontains=q))
    if merchant_id: reviews = reviews.filter(product__merchant_id=merchant_id)
    if rating: reviews = reviews.filter(rating=rating)
    
    merchants = filter_by_country(request.user, MerchantProfile.objects.all())
    return render(request, 'supervisor/admin_reviews_list.html', {'reviews': reviews, 'merchants': merchants})

@login_required
def process_return_refund(request, return_id):
    if not is_supervisor(request.user): return redirect('home')
    return_req = get_object_or_404(filter_by_country(request.user, ReturnRequest.objects.all()), id=return_id)
    order = return_req.order

    if request.method == 'POST':
        action = request.POST.get('action') 
        with transaction.atomic():
            merchant_wallet = Wallet.objects.select_for_update().get(id=order.merchant.wallet.id)
            if action == 'refund' and return_req.status == 'APPROVED':
                old_tx = WalletTransaction.objects.filter(wallet=merchant_wallet, description__icontains=f"#{order.id}", transaction_type='SALE').first()
                if old_tx:
                    WalletTransaction.objects.create(wallet=merchant_wallet, amount=-old_tx.amount, transaction_type='REFUND', description=f"خصم مرتجع #{order.id}", balance_after=merchant_wallet.balance - old_tx.amount)
                    merchant_wallet.balance -= old_tx.amount
                    merchant_wallet.save()
                order.status, return_req.status = 'RETURNED', 'REFUNDED'
                order.save(); return_req.save()
                messages.success(request, f"تمت تسوية المرتجع بنجاح.")
            elif action == 'approve':
                return_req.status = 'APPROVED'
                return_req.save()
                messages.success(request, "تم قبول المرتجع.")
            elif action == 'reject':
                return_req.status = 'REJECTED'
                return_req.save()
                messages.warning(request, "تم الرفض.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_returns_list'))

@login_required
def admin_notifications(request):
    if not is_supervisor(request.user): return redirect('home')
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'supervisor/admin_notifications.html', {'notifications': notifications})

@login_required
def super_manage_popups(request):
    if not is_supervisor(request.user): return redirect('home')
    active_offers = filter_by_country(request.user, Offer.objects.filter(is_active=True, end_date__gt=timezone.now()))

    if request.method == 'POST':
        title, custom_link, offer_id = request.POST.get('title'), request.POST.get('custom_link'), request.POST.get('offer_id')
        start_time, end_time = request.POST.get('start_time'), request.POST.get('end_time')
        is_active = request.POST.get('is_active') == 'on' 
        image = request.FILES.get('image')
        c = request.user.country if str(request.user.role) != 'OWNER' else None

        try:
            selected_offer = Offer.objects.get(id=offer_id) if offer_id else None
            popup = PromoPopup(country=c, title=title, custom_link=custom_link, offer=selected_offer, start_time=start_time, end_time=end_time, is_active=is_active, image=image)
            popup.clean()
            popup.save()
            messages.success(request, "تم جدولة الإعلان المنبثق بنجاح! 🚀")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
        return redirect('super_manage_popups')

    popups = filter_by_country(request.user, PromoPopup.objects.all()).order_by('-is_active', '-start_time')
    return render(request, 'supervisor/manage_popups.html', {'popups': popups, 'active_offers': active_offers})

@login_required
def super_toggle_popup(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    popup = get_object_or_404(filter_by_country(request.user, PromoPopup.objects.all()), pk=pk)
    if popup.is_active:
        popup.is_active = False
        popup.save()
        messages.success(request, "تم إيقاف الإعلان بنجاح.")
    return redirect('super_manage_popups')

@login_required
def super_delete_popup(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    popup = get_object_or_404(filter_by_country(request.user, PromoPopup.objects.all()), pk=pk)
    popup.delete()
    messages.success(request, "تم حذف الإعلان نهائياً.")
    return redirect('super_manage_popups')

@login_required
def manage_countries(request):
    if str(request.user.role) != 'OWNER' and not request.user.is_superuser:
        return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            Country.objects.create(
                name=request.POST.get('name'), code=request.POST.get('code').upper(), phone_code=request.POST.get('phone_code'),
                currency_name=request.POST.get('currency_name'), currency_symbol=request.POST.get('currency_symbol'),
                paymob_integration_id_card=request.POST.get('paymob_card', ''), paymob_integration_id_wallet=request.POST.get('paymob_wallet', ''),
                is_active=request.POST.get('is_active') == 'on'
            )
            messages.success(request, "تمت إضافة الدولة بنجاح 🌍")
        elif action == 'edit':
            country = get_object_or_404(Country, id=request.POST.get('country_id'))
            country.name, country.code, country.phone_code = request.POST.get('name'), request.POST.get('code').upper(), request.POST.get('phone_code')
            country.currency_name, country.currency_symbol = request.POST.get('currency_name'), request.POST.get('currency_symbol')
            country.paymob_integration_id_card, country.paymob_integration_id_wallet = request.POST.get('paymob_card', ''), request.POST.get('paymob_wallet', '')
            country.is_active = request.POST.get('is_active') == 'on'
            country.save()
            messages.success(request, "تم تحديث بيانات الدولة ✏️")
            
        return redirect('super_manage_countries')
        
    countries = Country.objects.all().order_by('-is_active', 'name')
    return render(request, 'supervisor/manage_countries.html', {'countries': countries})

@login_required
def delete_country(request, pk):
    if str(request.user.role) != 'OWNER' and not request.user.is_superuser:
        return redirect('home')
    try:
        Country.objects.filter(pk=pk).delete()
        messages.success(request, "تم حذف الدولة.")
    except ProtectedError:
        messages.error(request, "لا يمكن الحذف! يوجد مستخدمين أو منتجات مرتبطة بهذه الدولة. قم بتعطيلها بدلاً من الحذف.")
    return redirect('super_manage_countries')

@login_required
def manage_governorates(request):
    if not is_supervisor(request.user): 
        return redirect('home')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            country = get_object_or_404(Country, id=request.POST.get('country_id'))
            if str(request.user.role) != 'OWNER' and not request.user.is_superuser and country != request.user.country:
                messages.error(request, "غير مصرح لك.")
                return redirect('super_manage_governorates')
                    
            gov = Governorate.objects.create(country=country, name=request.POST.get('name'))
            save_dynamic_translations(request, gov, ['name'])
            gov.save()
            messages.success(request, f"تمت إضافة محافظة '{request.POST.get('name')}' بنجاح 📍")
            
        elif action == 'edit':
            gov = get_object_or_404(Governorate, id=request.POST.get('gov_id'))
            if str(request.user.role) != 'OWNER' and not request.user.is_superuser and gov.country != request.user.country:
                messages.error(request, "غير مصرح لك.")
                return redirect('super_manage_governorates')
                    
            gov.name = request.POST.get('name')
            save_dynamic_translations(request, gov, ['name'])
            gov.save()
            messages.success(request, "تم تحديث بيانات المحافظة ✏️")
            
        elif action == 'delete':
            gov = get_object_or_404(Governorate, id=request.POST.get('gov_id'))
            if str(request.user.role) != 'OWNER' and not request.user.is_superuser and gov.country != request.user.country:
                return redirect('super_manage_governorates')
            try:
                gov.delete()
                messages.success(request, "تم حذف المحافظة 🗑️")
            except ProtectedError:
                messages.error(request, "لا يمكن الحذف لارتباطها بطلبات أو إعدادات شحن.")
            
        return redirect('super_manage_governorates')

    governorates = filter_by_country(request.user, Governorate.objects.all()).select_related('country').order_by('country__name', 'name')
    
    if str(request.user.role) == 'OWNER' or request.user.is_superuser:
        countries = Country.objects.filter(is_active=True)
    else:
        countries = [request.user.country]

    return render(request, 'supervisor/manage_governorates.html', {
        'governorates': governorates,
        'countries': countries
    })

@login_required
def delete_governorate(request, pk):
    return redirect('super_manage_governorates')

@login_required
def system_translations_view(request):
    if not is_supervisor(request.user): return redirect('home')
    
    if request.method == 'POST':
        model_name = request.POST.get('model_name')
        item_id = request.POST.get('item_id')
        
        try:
            if model_name == 'Category':
                obj = Category.objects.get(id=item_id)
                obj.name_en = request.POST.get('name_en')
                obj.save()
            elif model_name == 'Governorate':
                obj = Governorate.objects.get(id=item_id)
                obj.name_en = request.POST.get('name_en')
                obj.save()
            elif model_name == 'TermsAndCondition':
                obj = TermsAndCondition.objects.get(id=item_id)
                obj.title_en, obj.content_en = request.POST.get('title_en'), request.POST.get('content_en')
                obj.save()
            elif model_name == 'AboutUs':
                obj = AboutUs.objects.get(id=item_id)
                obj.content_en = request.POST.get('content_en')
                obj.save()

            messages.success(request, "تم حفظ الترجمة بنجاح ✅")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {e}")
            
        return redirect('super_system_translations') 

    context = {
        'categories': Category.objects.all(),
        'governorates': filter_by_country(request.user, Governorate.objects.all()),
        'terms': filter_by_country(request.user, TermsAndCondition.objects.all()),
        'about_us': filter_by_country(request.user, AboutUs.objects.all())
    }
    return render(request, 'supervisor/translations.html', context)


# ==========================================
# 👑 لوحة تحكم المالك (المدير العام)
# ==========================================
def get_live_rates():
    rates = cache.get('live_usd_rates')
    if not rates:
        try:
            r = requests.get('https://open.er-api.com/v6/latest/USD', timeout=5)
            if r.status_code == 200:
                rates = r.json().get('rates', {})
                cache.set('live_usd_rates', rates, 43200) 
        except:
            rates = {}
    return rates or {}

@login_required
def owner_dashboard(request):
    if str(request.user.role) != 'OWNER' and not request.user.is_superuser:
        return redirect('supervisor_dashboard')

    today = timezone.now().date()
    six_months_ago = today - timedelta(days=180)
    live_rates = get_live_rates()
    currency_map = {'EG': 'EGP', 'SA': 'SAR', 'AE': 'AED', 'KW': 'KWD', 'JO': 'JOD', 'QA': 'QAR'}
    countries = Country.objects.filter(is_active=True)
    
    global_net_usd = Decimal('0.00')
    global_sales_usd = Decimal('0.00')
    detailed_data, exchange_ticker = {}, [] 

    for c in countries:
        c_code = currency_map.get(c.code, 'USD')
        rate = Decimal(str(live_rates.get(c_code, 1.0)))
        
        if rate > 0: exchange_ticker.append(f"1 USD = {rate:.2f} {c.currency_symbol}")

        c_users = User.objects.filter(country=c, role='CUSTOMER', is_banned=False).count()
        c_merchants = MerchantProfile.objects.filter(user__country=c, is_approved=True, user__is_banned=False).count()
        c_banned = User.objects.filter(country=c, is_banned=True).count()
        
        c_products_active = Product.objects.filter(merchant__user__country=c, is_active=True, is_approved=True).count()
        c_products_pending = Product.objects.filter(merchant__user__country=c, is_approved=False).count()
        
        orders = Order.objects.filter(Q(customer__country=c) | Q(merchant__user__country=c)).distinct()
        
        o_delivered = orders.filter(status='DELIVERED').count()
        o_returned = orders.filter(status='RETURNED').count()
        o_pending = orders.filter(status__in=['PENDING', 'PROCESSING', 'SHIPPED']).count()
        
        sales_local = orders.filter(status='DELIVERED').aggregate(s=Sum('final_total'))['s'] or Decimal('0.00')
        returns_local = orders.filter(status='RETURNED').aggregate(s=Sum('final_total'))['s'] or Decimal('0.00')
        
        commissions = sales_local * Decimal('0.10')
        compensations = returns_local * Decimal('0.02') 
        net_profit = commissions - compensations

        if rate > 0:
            global_sales_usd += (sales_local / rate)
            global_net_usd += (net_profit / rate)

        c_complaints = SupportTicket.objects.filter(customer__country=c).count()
        trends = orders.filter(status='DELIVERED', created_at__date__gte=six_months_ago).annotate(m=TruncMonth('created_at')).values('m').annotate(total=Sum('final_total')).order_by('m')
        
        trend_labels = [t['m'].strftime('%b') for t in trends]
        trend_values = [float(t['total']) for t in trends]

        detailed_data[c.id] = {
            'name': c.name, 'code': c.code, 'flag': f"https://flagcdn.com/w160/{c.code.lower()}.png",
            'currency': c.currency_symbol, 'rate_to_usd': float(rate),
            'orders': {'delivered': o_delivered, 'returned': o_returned, 'pending': o_pending},
            'finance': {'sales': float(sales_local), 'commissions': float(commissions), 'compensations': float(compensations), 'net_profit': float(net_profit)},
            'people': {'users': c_users, 'merchants': c_merchants, 'banned': c_banned, 'complaints': c_complaints},
            'products': {'active': c_products_active, 'pending': c_products_pending},
            'charts': {'labels': trend_labels, 'data': trend_values}
        }

    context = {
        'global_sales_usd': float(global_sales_usd),
        'global_net_usd': float(global_net_usd),
        'exchange_ticker': "   |   ".join(exchange_ticker),
        'countries_json': json.dumps(detailed_data, cls=DjangoJSONEncoder),
        'countries_list': countries,
    }
    return render(request, 'supervisor/owner_dashboard.html', context)


@login_required
def archived_products(request):
    """عرض المنتجات المؤرشفة للإدارة"""
    if not is_supervisor(request.user): return redirect('home')
    
    # جلب المنتجات المؤرشفة فقط
    products = filter_by_country(request.user, Product.objects.filter(is_archived=True)).order_by('-created_at')
    return render(request, 'supervisor/archived_products.html', {'products': products})

@login_required
def restore_archived_product(request, pk):
    """استعادة منتج مؤرشف للتاجر (عن طريق الإدارة)"""
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(filter_by_country(request.user, Product.objects.all()), pk=pk)
    
    # إرجاع المنتج لحالة التوقف (غير نشط ولكن غير مؤرشف) ليظهر للتاجر ويعدله
    product.is_archived = False
    product.is_active = False 
    product.save()
    
    from store.utils import send_notification
    send_notification(product.merchant.user, "استعادة منتج 📦", f"بناءً على طلبك، قام الدعم الفني باستعادة منتج '{product.name}'.", "/merchant/products/")
    
    messages.success(request, f"تمت استعادة المنتج '{product.name}' بنجاح وإعادته للتاجر.")
    return redirect('super_archived_products')