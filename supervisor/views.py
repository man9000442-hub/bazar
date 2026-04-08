# ==========================================
# 1. الاستدعاءات الأساسية (Imports)
# ==========================================
import csv
import json
import requests
from decimal import Decimal
from datetime import datetime, timedelta
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.crypto import get_random_string
from django.http import HttpResponse
from django.db import transaction
from django.db.models import Count, Sum, Q, F, ProtectedError
from django.db.models.functions import TruncDay, TruncMonth
from django.conf import settings

# الموديلات
from accounts.models import User, CustomRole, Country
from store.models import (
    Product, Order, MerchantProfile, DepositRequest, 
    WithdrawalRequest, Offer, Category, SiteSetting, OrderItem,
    ProductReview, Wallet, WalletTransaction, Notification, Banner,
    DeliveryComplaint, PersonalVoucher, AboutUs, TermsAndCondition,
    MerchantShippingRate, PaymobTransaction, ReturnRequest, ProductSize, ProductImage, PromoPopup, Governorate
)
from support.models import SupportTicket, TicketMessage

# ==========================================
# 🔥 إعداد دوال الإشعارات (تم إزالة الكتمان للعمل بكفاءة)
# ==========================================
from store.utils import send_notification, notify_admins, send_push_to_user

# ==========================================
# 🔥 2. دوال مساعدة للفلترة الذكية (الدول والصلاحيات)
# ==========================================
def is_supervisor(user):
    """التحقق من صلاحيات الدخول للوحة الإدارة (تم إضافة COUNTRY_ADMIN)"""
    return user.is_superuser or user.role in [User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3, User.Role.COUNTRY_ADMIN, User.Role.OWNER]

def get_country_kwargs(user, prefix=''):
    """
    دالة سحرية لفلترة البيانات بناءً على دولة المشرف.
    إذا كان المالك (OWNER)، لا تطبق أي فلتر (يرى الجميع).
    إذا كان مشرف دولة، تطبق الفلتر على دولته فقط.
    """
    if user.is_superuser or user.role == 'OWNER':
        return {} # المالك يرى كل شيء
    return {f"{prefix}country": user.country}


# ==========================================
# 3. لوحة التحكم والإحصائيات (Dashboard)
# ==========================================
@login_required
def supervisor_dashboard(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # تجهيز فلاتر الدولة لكل موديل
    c_kwargs = get_country_kwargs(request.user)
    m_kwargs = get_country_kwargs(request.user, 'merchant__user__')
    u_kwargs = get_country_kwargs(request.user, 'user__')
    cust_kwargs = get_country_kwargs(request.user, 'customer__')

    # 1. الإحصائيات العامة (Counters) مضاف لها فلتر الدولة
    pending_orders = Order.objects.filter(status=Order.Status.PENDING, **c_kwargs).count()
    pending_products = Product.objects.filter(is_active=False, **c_kwargs).count()
    pending_deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING, **m_kwargs).count()
    new_merchants = MerchantProfile.objects.filter(is_approved=False, **u_kwargs).count()
    open_tickets_count = SupportTicket.objects.filter(status='OPEN', **cust_kwargs).count()   

    # 2. المبيعات الحقيقية
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    valid_statuses = ['PENDING', 'SHIPPED', 'DELIVERED']
    
    sales_today = Order.objects.filter(status__in=valid_statuses, created_at__date=today, **c_kwargs).aggregate(Sum('final_total'))['final_total__sum'] or 0
    sales_month = Order.objects.filter(status__in=valid_statuses, created_at__date__gte=start_of_month, **c_kwargs).aggregate(Sum('final_total'))['final_total__sum'] or 0

    # 3. الرسم البياني (آخر 7 أيام)
    last_7_days = today - timedelta(days=6)
    chart_data = Order.objects.filter(
        status__in=valid_statuses, created_at__date__gte=last_7_days, **c_kwargs
    ).annotate(day=TruncDay('created_at')).values('day').annotate(total=Sum('final_total')).order_by('day')

    days_labels, sales_values = [], []
    current_date = last_7_days
    data_dict = {entry['day'].date() if hasattr(entry['day'], 'date') else entry['day']: entry['total'] for entry in chart_data}
    
    for i in range(7):
        day_val = data_dict.get(current_date, 0)
        days_labels.append(current_date.strftime("%d %b"))
        sales_values.append(float(day_val))
        current_date += timedelta(days=1)

    # 4. آخر 5 طلبات (لدولته فقط)
    recent_orders = Order.objects.filter(**c_kwargs).select_related('customer').order_by('-created_at')[:5]

    context = {
        'pending_orders': pending_orders, 'pending_products': pending_products,
        'pending_deposits': pending_deposits, 'new_merchants': new_merchants,
        'open_tickets_count': open_tickets_count, 'sales_today': float(sales_today),
        'sales_month': float(sales_month), 'chart_labels': json.dumps(days_labels),
        'chart_data': json.dumps(sales_values), 'recent_orders': recent_orders,
    }
    return render(request, 'supervisor/dashboard.html', context)


# ==========================================
# 4. إدارة الطلبات (Orders)
# ==========================================
@login_required
def all_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    status = request.GET.get('status')
    orders = Order.objects.filter(**get_country_kwargs(request.user)).exclude(status=Order.Status.CART).order_by('-created_at')
    if status: orders = orders.filter(status=status)
    return render(request, 'supervisor/all_orders.html', {'orders': orders})

@login_required
def order_detail(request, order_id):
    if not is_supervisor(request.user): return redirect('home')
    order = get_object_or_404(Order, order_id=order_id, **get_country_kwargs(request.user))
    
    # معالجة تغيير حالة الطلب
    if request.method == 'POST' and request.user.has_perm_access('orders'):
        new_status = request.POST.get('status')
        if new_status in dict(Order.Status.choices):
            order.status = new_status
            order.save()
            
            # إرسال إشعار للعميل بتغير حالة طلبه
            send_notification(order.customer, "تحديث حالة الطلب 📦", f"تم تحديث حالة طلبك #{order.order_id} إلى: {order.get_status_display()}", "/my-orders/")
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
    orders = Order.objects.filter(**get_country_kwargs(request.user)).exclude(status='CART').values_list('order_id', 'customer__first_name', 'shipping_phone', 'final_total', 'status', 'created_at')
    for order in orders: writer.writerow(order)
    return response


# ==========================================
# 5. إدارة المنتجات (Products)
# ==========================================
@login_required
def all_products(request):
    if not is_supervisor(request.user): return redirect('home')
    products = Product.objects.filter(**get_country_kwargs(request.user)).annotate(
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
    products = Product.objects.filter(is_approved=False, **get_country_kwargs(request.user)).order_by('-created_at')
    return render(request, 'supervisor/pending_products.html', {'products': products})

@login_required
def product_review(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(Product, pk=pk, **get_country_kwargs(request.user))
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            product.commission_pct = request.POST.get('commission')
            product.is_approved = True 
            product.is_active = True
            product.save()
            
            send_notification(product.merchant.user, "تم قبول منتجك! ✅", f"تم اعتماد منتج '{product.name}' وهو الآن معروض للبيع.", "/merchant/products/")
            send_push_to_user(product.merchant.user, "منتج مقبول ✅", f"تمت الموافقة على منتج '{product.name}' ونشره في المتجر.")
            messages.success(request, f"تم اعتماد المنتج {product.name}")
            
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
    product = get_object_or_404(Product, pk=pk, **get_country_kwargs(request.user))
    if request.method == 'POST':
        product.is_active = request.POST.get('is_active') == 'on'
        product.commission_pct = request.POST.get('commission')
        product.save()
        messages.success(request, "تم تحديث المنتج.")
        return redirect('super_all_products')
    return render(request, 'supervisor/product_edit_admin.html', {'product': product})

@login_required
def delete_product_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(Product, pk=pk, **get_country_kwargs(request.user))
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
    merchants = MerchantProfile.objects.filter(is_approved=True, **get_country_kwargs(request.user, 'user__'))
    return render(request, 'supervisor/merchants_list.html', {'merchants': merchants})

@login_required
def pending_merchants(request):
    if not is_supervisor(request.user): return redirect('home')
    merchants = MerchantProfile.objects.filter(is_approved=False, **get_country_kwargs(request.user, 'user__'))
    return render(request, 'supervisor/pending_merchants.html', {'merchants': merchants})

@login_required
def approve_merchant(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))
    merchant.is_approved = True
    rank = request.POST.get('verification_rank', 'NONE')
    merchant.verification_rank = rank
    merchant.is_verified = True if rank != 'NONE' else False
    
    if request.GET.get('verify') == 'true':
        merchant.is_verified = True
        msg = f"تم تفعيل وتوثيق التاجر {merchant.user.first_name} بنجاح! 🌟"
    else:
        msg = f"تم تفعيل التاجر {merchant.user.first_name}"
    merchant.save()
    
    send_notification(merchant.user, "تم تفعيل متجرك! 🎉", "مبروك! تمت الموافقة على متجرك ويمكنك الآن إضافة منتجاتك.", "/merchant/dashboard/")
    send_push_to_user(merchant.user, "مبروك تفعيل المتجر! 🎉", "تم تفعيل حسابك كتاجر، ابدأ الآن بإضافة منتجاتك.")
    messages.success(request, msg)
    return redirect('super_pending_merchants')

@login_required
def reject_merchant(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))
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
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))
    merchant.is_verified = not merchant.is_verified
    merchant.save()
    status = "تم توثيق" if merchant.is_verified else "إلغاء توثيق"
    messages.success(request, f"{status} التاجر {merchant.user.first_name}")
    return redirect(request.META.get('HTTP_REFERER', 'super_users_list'))

@login_required
def update_merchant_limit(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))
    if request.method == 'POST':
        new_limit = request.POST.get('product_limit')
        if new_limit and new_limit.isdigit(): merchant.product_limit = int(new_limit)
        merchant.subscription_end_date = request.POST.get('subscription_end_date') or None 
        min_balance = request.POST.get('minimum_balance_required')
        if min_balance:
            try: merchant.minimum_balance_required = float(min_balance)
            except ValueError: pass 
        merchant.save()
        messages.success(request, f"تم تحديث صلاحيات التاجر ({merchant.user.first_name}).")
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def hide_merchant_products(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))
    
    Product.objects.filter(merchant=merchant).update(is_active=False)
    
    send_notification(merchant.user, "إيقاف المنتجات ⚠️", "تم إيقاف عرض جميع منتجاتك إدارياً، يرجى مراجعة الدعم الفني.")
    send_push_to_user(merchant.user, "إيقاف المنتجات ⚠️", "تم إيقاف منتجاتك مؤقتاً بواسطة الإدارة.")
    messages.success(request, f"تم إخفاء منتجات التاجر بنجاح ✅")
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def show_merchant_products(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))
    
    Product.objects.filter(merchant=merchant, is_approved=True).update(is_active=True)
    
    send_notification(merchant.user, "تفعيل المنتجات ✅", "تم إعادة تفعيل وعرض منتجاتك على المنصة بنجاح.")
    send_push_to_user(merchant.user, "تفعيل المنتجات ✅", "تم إرجاع منتجاتك للظهور على المنصة بنجاح.")
    messages.success(request, f"تم إظهار منتجات التاجر المقبولة فقط بنجاح ✅")
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def merchant_profile_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk, **get_country_kwargs(request.user, 'user__'))

    if request.method == 'POST':
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
    users = User.objects.filter(**get_country_kwargs(request.user)).order_by('-date_joined')
    if role: users = users.filter(role=role)
    if q: users = users.filter(Q(username__icontains=q) | Q(phone_primary__icontains=q))
    return render(request, 'supervisor/users_list.html', {'users': users})

@login_required
def user_edit(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_obj = get_object_or_404(User, pk=user_id, **get_country_kwargs(request.user))
    
    if request.method == 'POST':
        if request.POST.get('first_name'): user_obj.first_name = request.POST.get('first_name')
        if request.POST.get('last_name'): user_obj.last_name = request.POST.get('last_name')
        if request.POST.get('phone'):
            user_obj.phone_primary = request.POST.get('phone')
            user_obj.username = request.POST.get('phone') 
        if request.POST.get('email'): user_obj.email = request.POST.get('email')

        role = request.POST.get('role')
        if role: user_obj.role = role
        
        # 🔥 إضافة حفظ الدولة الجديدة
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
        
    # 🔥 جلب الدول النشطة لإرسالها للواجهة (Template)
    countries = Country.objects.filter(is_active=True)
    return render(request, 'supervisor/user_edit.html', {
        'user_obj': user_obj, 
        'countries': countries
    })

@login_required
def user_delete(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_to_delete = get_object_or_404(User, id=user_id, **get_country_kwargs(request.user))
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
    users = User.objects.filter(is_banned=True, **get_country_kwargs(request.user))
    return render(request, 'supervisor/banned_users.html', {'users': users})

@login_required
def ban_user(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user = get_object_or_404(User, pk=user_id, **get_country_kwargs(request.user))
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

    base_users = User.objects.filter(role='CUSTOMER', **get_country_kwargs(request.user))
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
    customer = get_object_or_404(User, pk=user_id, **get_country_kwargs(request.user))
    orders = Order.objects.filter(customer=customer).order_by('-created_at')
    total_spent = orders.filter(status='DELIVERED').aggregate(Sum('final_total'))['final_total__sum'] or 0
    return render(request, 'supervisor/customer_profile.html', {'customer': customer, 'orders': orders, 'total_spent': total_spent})


# ==========================================
# 8. الإدارة المالية والمحافظ (Finance & Wallets)
# ==========================================
@login_required
def pending_deposits(request):
    if not is_supervisor(request.user): return redirect('home')
    deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING, **get_country_kwargs(request.user, 'merchant__user__')).order_by('-created_at')
    return render(request, 'supervisor/pending_deposits.html', {'deposits': deposits})

@login_required
def approve_deposit(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    deposit = get_object_or_404(DepositRequest, pk=pk, **get_country_kwargs(request.user, 'merchant__user__'))
    deposit.status = DepositRequest.Status.APPROVED
    deposit.save()
    send_notification(deposit.merchant.user, "تم قبول الإيداع 💰", "تم مراجعة وقبول طلب الإيداع الخاص بك.", "/merchant/wallet/")
    send_push_to_user(deposit.merchant.user, "قبول إيداع 💰", "تمت الموافقة على طلب إيداعك وإضافته لمحفظتك.")
    messages.success(request, "تم قبول الإيداع.")
    return redirect('super_pending_deposits')

@login_required
def pending_withdrawals(request):
    if not is_supervisor(request.user): return redirect('home')
    withdrawals = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING, **get_country_kwargs(request.user, 'merchant__user__')).order_by('-created_at')
    return render(request, 'supervisor/pending_withdrawals.html', {'withdrawals': withdrawals})

@login_required
def approve_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk, **get_country_kwargs(request.user, 'merchant__user__'))
    if withdrawal.status == 'PENDING':
        withdrawal.status = 'APPROVED'
        withdrawal.save()
        send_notification(withdrawal.merchant.user, "تم تحويل الأرباح 💸", f"تمت الموافقة على سحب {withdrawal.amount} وتحويلها إليك.", "/merchant/wallet/")
        send_push_to_user(withdrawal.merchant.user, "تحويل أرباح 💸", f"تم تحويل مبلغ {withdrawal.amount} بنجاح.")
        messages.success(request, f"تم تأكيد التحويل للتاجر {withdrawal.merchant.user.first_name}.")
    return redirect('super_pending_withdrawals')

@login_required
def reject_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    req = get_object_or_404(WithdrawalRequest, pk=pk, **get_country_kwargs(request.user, 'merchant__user__'))
    if req.status == 'PENDING':
        req.status = 'REJECTED'
        req.save()
        wallet = req.merchant.wallet
        wallet.balance += req.amount
        wallet.save()
        WalletTransaction.objects.create(
            wallet=wallet, amount=req.amount, transaction_type=WalletTransaction.TxType.COMPENSATION,
            description=f"استرداد لرفض طلب سحب #{req.id}", balance_after=wallet.balance, is_released=True
        )
        send_notification(req.merchant.user, "رفض طلب السحب ❌", f"تم رفض السحب وإعادة {req.amount} لمحفظتك. يرجى مراجعة الدعم.", "/merchant/wallet/")
        send_push_to_user(req.merchant.user, "رفض سحب ❌", f"تم رفض طلب سحبك وتم استرداد المبلغ للمحفظة.")
        messages.warning(request, f"تم رفض السحب وإعادة المبلغ للتاجر.")
    return redirect('super_pending_withdrawals')

@login_required
def wallets_list(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # التأكد من وجود محافظ لتجار الدولة المحددة
    for m in MerchantProfile.objects.filter(**get_country_kwargs(request.user, 'user__')): 
        Wallet.objects.get_or_create(merchant=m)
        
    wallets = Wallet.objects.filter(**get_country_kwargs(request.user, 'merchant__user__')).order_by('-balance')
    return render(request, 'supervisor/wallets_list.html', {'wallets': wallets})

@login_required
def adjust_wallet(request, wallet_id):
    if not is_supervisor(request.user): return redirect('home')
    wallet = get_object_or_404(Wallet, pk=wallet_id, **get_country_kwargs(request.user, 'merchant__user__'))
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount'))
        reason = request.POST.get('reason')
        action = request.POST.get('action') 
        
        with transaction.atomic():
            if action == 'add':
                wallet.balance += amount
                desc, msg = f"إضافة إدارية: {reason}", f"تم إضافة {amount} إدارياً لمحفظتك. السبب: {reason}"
            else:
                wallet.balance -= amount
                desc, msg = f"خصم إداري: {reason}", f"تم خصم {amount} إدارياً من محفظتك. السبب: {reason}"
            
            wallet.save()
            WalletTransaction.objects.create(
                wallet=wallet, amount=amount if action=='add' else -amount,
                transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=desc, balance_after=wallet.balance, is_released=True
            )
            
            # 1. إشعار التاجر اللي رصيده اتعدل
            send_notification(wallet.merchant.user, "تحديث رصيد المحفظة 💰", msg, "/merchant/wallet/")
            send_push_to_user(wallet.merchant.user, "تحديث بالمحفظة 💳", msg)
            
            # 2. إشعار للمديرين في الموقع
            notify_admins(
                title="تعديل رصيد يدوي ⚠️", 
                message=f"قام {request.user.first_name} بـ { 'إضافة' if action == 'add' else 'خصم' } مبلغ {amount} لمحفظة التاجر '{wallet.merchant.user.first_name}'. السبب: {reason}",
                link=reverse('super_wallets_list')  
            )
            
            # 🔥 3. إشعار بوش يوصلك إنت شخصياً (الآدمن اللي عمل التعديل) عشان تتأكد إن شغلك مسمع
            send_push_to_user(
                user=request.user, 
                title="تم التعديل بنجاح 💰", 
                body=f"تم {'إضافة' if action == 'add' else 'خصم'} {amount} لمحفظة التاجر '{wallet.merchant.user.first_name}'."
            )
            
            messages.success(request, "تم تعديل الرصيد بنجاح.")
            return redirect('super_wallets_list')
    return render(request, 'supervisor/adjust_wallet.html', {'wallet': wallet})

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

    base_qs = WalletTransaction.objects.filter(
        created_at__date__range=[start_date, end_date], 
        **get_country_kwargs(request.user, 'wallet__merchant__user__')
    )
    
    income_val = base_qs.filter(amount__lt=0, description__contains="خصم عمولة").aggregate(Sum('amount'))['amount__sum'] or 0
    income = abs(float(income_val))
    expenses = float(base_qs.filter(transaction_type=WalletTransaction.TxType.COMPENSATION).aggregate(Sum('amount'))['amount__sum'] or 0)
    net_profit = income - expenses
    total_merchants_balance = float(Wallet.objects.filter(**get_country_kwargs(request.user, 'merchant__user__')).aggregate(Sum('balance'))['balance__sum'] or 0)

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
    if not is_supervisor(request.user): return redirect('home')
    tx_type = request.GET.get('type')
    logs = WalletTransaction.objects.filter(**get_country_kwargs(request.user, 'wallet__merchant__user__')).select_related('wallet__merchant__user').order_by('-created_at')
    if tx_type: logs = logs.filter(transaction_type=tx_type)
    return render(request, 'supervisor/finance_logs.html', {'logs': logs})

@login_required
def export_profit_report(request):
    if not is_supervisor(request.user): return redirect('home')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="profits_report.csv"'
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['المعرف', 'التاجر', 'النوع', 'المبلغ', 'الوصف', 'التاريخ'])
    for tx in WalletTransaction.objects.filter(**get_country_kwargs(request.user, 'wallet__merchant__user__')).order_by('-created_at'):
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
    for w in Wallet.objects.filter(**get_country_kwargs(request.user, 'merchant__user__')):
        writer.writerow([w.merchant.user.first_name, w.merchant.user.phone_primary, w.balance, w.pending_balance])
    return response


# ==========================================
# 9. الإعدادات، العروض، الشروط والأقسام
# ==========================================
from decimal import Decimal, InvalidOperation

@login_required
def site_settings_view(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # تحديد الدولة بناءً على صلاحيات المستخدم
    current_country = request.user.country if request.user.role != 'OWNER' else None
    settings_obj = SiteSetting.get_settings(current_country)
    
    if request.method == 'POST':
        try:
            # 1. تحديث الهوية
            settings_obj.site_name = request.POST.get('site_name') or "Elbazaar"
            
            # 2. المالية (تحويل آمن لـ Decimal لمنع إيرور Not Null)
            settings_obj.platform_fee_fixed = Decimal(request.POST.get('fee_fixed') or '0.00')
            settings_obj.platform_fee_percentage = Decimal(request.POST.get('fee_percent') or '0.00')
            settings_obj.min_withdrawal_amount = Decimal(request.POST.get('min_withdrawal') or '0.00')
            settings_obj.min_wallet_balance = Decimal(request.POST.get('reserved_balance') or '0.00')
            settings_obj.min_active_balance = Decimal(request.POST.get('min_active') or '0.00')
            
            # 3. السياسات والدعوات (تحويل لـ Integer)
            settings_obj.pending_balance_release_hours = int(request.POST.get('release_hours') or 24)
            settings_obj.referral_reward_amount = Decimal(request.POST.get('ref_reward') or '0.00')
            settings_obj.referral_grace_period_hours = int(request.POST.get('ref_grace') or 24)
            settings_obj.referral_discount_limit_pct = int(request.POST.get('ref_limit') or 10)
            settings_obj.referral_reward_limit_orders = int(request.POST.get('ref_orders_limit') or 1)

            if request.FILES.get('banner'):
                settings_obj.banner_image = request.FILES.get('banner')
                  
            settings_obj.save()
            
            # إشعارات الموبايل والموقع
            notify_admins(title="تحديث الإعدادات ⚙️", message=f"قام {request.user.first_name} بتحديث إعدادات النظام.")
            send_push_to_user(request.user, "تم الحفظ بنجاح ✅", "تم تحديث إعدادات النظام في قاعدة البيانات.")
            
            messages.success(request, "تم حفظ الإعدادات بنجاح ✅")
            
        except (InvalidOperation, ValueError) as e:
            messages.error(request, f"🚨 خطأ في البيانات: يرجى التأكد من إدخال أرقام صحيحة.")
        except Exception as e:
            messages.error(request, f"🚨 حدث خطأ غير متوقع: {str(e)}")
            
        return redirect('super_site_settings')
        
    return render(request, 'supervisor/site_settings.html', {'settings': settings_obj})

@login_required
def manage_categories(request):
    if not is_supervisor(request.user): return redirect('home')
    if request.method == 'POST':
        Category.objects.create(name=request.POST.get('name'), image=request.FILES.get('image'))
        return redirect('super_categories')
    return render(request, 'supervisor/categories.html', {'categories': Category.objects.all()})

@login_required
def edit_category(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.name = request.POST.get('name')
        if request.FILES.get('image'): category.image = request.FILES.get('image')
        category.save()
        messages.success(request, "تم تعديل القسم بنجاح ✅")
    return redirect('super_categories')

@login_required
def delete_category(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    Category.objects.filter(pk=pk).delete()
    return redirect('super_categories')

@login_required
def manage_offers(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    offers = Offer.objects.filter(is_platform_offer=True, **get_country_kwargs(request.user, 'product__')).order_by('-created_at')
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
        
        product = get_object_or_404(Product, pk=product_id, **get_country_kwargs(request.user))
        Offer.objects.update_or_create(
            product=product,
            defaults={
                'discount_percentage': percentage, 'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=days),
                'is_active': True, 'is_platform_offer': True,
                'free_shipping': free_shipping, 'free_shipping_threshold': threshold
            }
        )
        send_notification(product.merchant.user, "عرض منصة جديد! 🏷️", f"قامت المنصة بتفعيل عرض {percentage}% على منتج '{product.name}'.", "/merchant/products/")
        send_push_to_user(product.merchant.user, "عرض مميز لمنتجك! 🏷️", f"إدارة المنصة أضافت عرض بخصم {percentage}% على '{product.name}'.")
        messages.success(request, "تم إطلاق عرض المنصة!")
        return redirect('supervisor_dashboard')
    return render(request, 'supervisor/create_offer.html', {'products': Product.objects.filter(is_active=True, **get_country_kwargs(request.user))})

@login_required
def delete_offer_admin(request, pk):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    Offer.objects.filter(pk=pk, **get_country_kwargs(request.user, 'product__')).delete()
    messages.success(request, "تم حذف العرض.")
    return redirect('super_manage_offers')

@login_required
def manage_banners(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    if request.method == 'POST':
        c = request.user.country if request.user.role != 'OWNER' else None
        Banner.objects.create(country=c, image=request.FILES.get('image'), link=request.POST.get('link'), expires_at=request.POST.get('expires_at') or None)
        messages.success(request, "تم إضافة البانر بنجاح.")
        return redirect('super_manage_banners')
    return render(request, 'supervisor/manage_banners.html', {'banners': Banner.objects.filter(**get_country_kwargs(request.user)).order_by('-created_at')})

@login_required
def delete_banner(request, pk):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    Banner.objects.filter(pk=pk, **get_country_kwargs(request.user)).delete()
    messages.success(request, "تم الحذف.")
    return redirect('super_manage_banners')

@login_required
def manage_terms(request):
    if not is_supervisor(request.user): return redirect('home')
        
    if request.method == 'POST':
        action = request.POST.get('action') 
        c = request.user.country if request.user.role != 'OWNER' else None
        
        if action == 'add':
            TermsAndCondition.objects.create(
                country=c,
                title=request.POST.get('title'), 
                content=request.POST.get('content'),
                order=request.POST.get('order', 1), 
                document_type=request.POST.get('document_type'),
                user_type=request.POST.get('user_type')
            )
            messages.success(request, "تمت إضافة البند بنجاح ✅")
            
        elif action == 'edit':
            term_id = request.POST.get('term_id')
            term = get_object_or_404(TermsAndCondition, id=term_id, **get_country_kwargs(request.user))
            term.title = request.POST.get('title')
            term.content = request.POST.get('content')
            term.order = request.POST.get('order', 1)
            term.document_type = request.POST.get('document_type')
            term.user_type = request.POST.get('user_type')
            term.is_active = request.POST.get('is_active') == 'on' 
            term.save()
            messages.success(request, "تم تحديث البند بنجاح ✏️")
            
        elif action == 'delete':
            term_id = request.POST.get('term_id')
            term = get_object_or_404(TermsAndCondition, id=term_id, **get_country_kwargs(request.user))
            term.delete()
            messages.success(request, "تم حذف البند بنجاح 🗑️")
            
        return redirect('super_manage_terms')

    terms = TermsAndCondition.objects.filter(**get_country_kwargs(request.user)).order_by('document_type', 'user_type', 'order')
    return render(request, 'supervisor/manage_terms.html', {'terms': terms})

@login_required
def edit_term(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    term = get_object_or_404(TermsAndCondition, pk=pk, **get_country_kwargs(request.user))
    if request.method == 'POST':
        term.title = request.POST.get('title')
        term.content = request.POST.get('content')
        term.order = request.POST.get('order', 1)
        term.document_type = request.POST.get('document_type') 
        term.user_type = request.POST.get('user_type')        
        term.save()
        messages.success(request, "تم تعديل البند بنجاح ✅")
    return redirect('super_manage_terms')

@login_required
def delete_term(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    TermsAndCondition.objects.filter(pk=pk, **get_country_kwargs(request.user)).delete()
    return redirect('super_manage_terms')

@login_required
def edit_about_us(request):
    if not is_supervisor(request.user): return redirect('home')
    c = request.user.country if request.user.role != 'OWNER' else None
    about, created = AboutUs.objects.get_or_create(country=c)
    if request.method == 'POST':
        about.content = request.POST.get('content')
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
            customer = get_object_or_404(User, id=request.POST.get('customer_id'), **get_country_kwargs(request.user))
            PersonalVoucher.objects.create(
                customer=customer, title=request.POST.get('title'), code=code.upper(),
                discount_percentage=request.POST.get('discount_percentage', 0),
                max_discount_amount=request.POST.get('max_discount_amount', 0),
                remaining_items=request.POST.get('remaining_items', 1),
                free_shipping=request.POST.get('free_shipping') == 'on',
                expires_at=request.POST.get('expires_at')
            )
            send_notification(customer, "هدية خاصة لك! 🎁", f"لقد حصلت على قسيمة خصم: {code}. استمتع بالتسوق!", "/cart/")
            send_push_to_user(customer, "كوبون خصم هدية! 🎁", f"استخدم الكوبون ({code}) واستمتع بخصم على مشترياتك.")
            messages.success(request, f"تم إرسال العرض بنجاح للعميل {customer.first_name} ✅")
            return redirect('super_manage_vouchers')

    customers = User.objects.filter(is_superuser=False, **get_country_kwargs(request.user)).order_by('-date_joined')
    vouchers = PersonalVoucher.objects.filter(**get_country_kwargs(request.user, 'customer__')).order_by('-created_at')
    return render(request, 'supervisor/manage_vouchers.html', {'customers': customers, 'vouchers': vouchers, 'suggested_code': get_random_string(length=8).upper()})

@login_required
def delete_voucher(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    get_object_or_404(PersonalVoucher, pk=pk, **get_country_kwargs(request.user, 'customer__')).delete()
    messages.success(request, "تم حذف القسيمة بنجاح.")
    return redirect('super_manage_vouchers')


# ==========================================
# 🔥 10. فريق العمل (تعديل صلاحيات مدراء الدول)
# ==========================================
AVAILABLE_PERMISSIONS = [
    ('orders', 'إدارة الطلبات'), ('products', 'إدارة المنتجات'), ('categories', 'إدارة الأقسام'),
    ('users', 'إدارة المستخدمين'), ('merchants', 'تفعيل التجار'), ('finance', 'المالية والسحوبات'),
    ('settings', 'إعدادات الموقع'), ('support', 'الدعم الفني'), ('team', 'فريق العمل'),
    ('offers', 'إدارة العروض'), ('notifications', 'إرسال إشعارات'), ('banners', 'إدارة البانرات الإعلانية'),
]

@login_required
def team_management(request):
    # السماح للمالك ومدير الدولة فقط بإضافة مشرفين
    if not (request.user.is_superuser or request.user.role in ['OWNER', 'COUNTRY_ADMIN']): 
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
                
                # 🔥 هنا الذكاء في تحديد الرتبة والدولة
                if request.user.role == 'OWNER':
                    country_id = request.POST.get('country_id')
                    base_role = request.POST.get('base_role')
                    
                    if country_id:
                        new_admin.country = Country.objects.get(id=country_id)
                    new_admin.role = base_role if base_role else User.Role.ADMIN_LVL3
                else:
                    new_admin.country = request.user.country
                    new_admin.role = User.Role.ADMIN_LVL3
                    
                # إضافة الصلاحيات المخصصة (Custom Role) إن وجدت
                role_id = request.POST.get('custom_role')
                if role_id:
                    new_admin.custom_role = CustomRole.objects.get(id=role_id)
                    
                new_admin.save()
                
                notify_admins(title="إضافة مشرف جديد 🛡️", message=f"قام {request.user.first_name} بتعيين مشرف جديد بالنظام.", link=reverse('super_team'))
                # 🔥 إشعار بوش للآدمن
                send_push_to_user(request.user, "مشرف جديد 🛡️", f"تم تعيين المشرف {username} بنجاح.")
                
                messages.success(request, f"تم تعيين المشرف {username} بنجاح ✅")
            except Exception as e: 
                messages.error(request, f"حدث خطأ: {e}")
                
        return redirect('super_team')
        
    # جلب فريق العمل بناءً على صلاحيات المشرف الحالي
    team = User.objects.filter(role__in=[User.Role.COUNTRY_ADMIN, User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3], **get_country_kwargs(request.user)).exclude(pk=request.user.pk)
    
    # جلب الدول عشان نظهرها في الفورم للمالك فقط
    countries = Country.objects.filter(is_active=True) if request.user.role == 'OWNER' else None
    
    return render(request, 'supervisor/team_management.html', {
        'team': team, 
        'custom_roles': CustomRole.objects.filter(**get_country_kwargs(request.user)),
        'countries': countries
    })


@login_required
def manage_roles(request):
    if not (request.user.is_superuser or request.user.role in ['OWNER', 'COUNTRY_ADMIN']): 
        return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        c = request.user.country if request.user.role != 'OWNER' else None
        CustomRole.objects.create(country=c, name=request.POST.get('name'), permissions=",".join(request.POST.getlist('permissions')))
        messages.success(request, "تم إنشاء الدور بنجاح.")
        return redirect('super_manage_roles')
    return render(request, 'supervisor/manage_roles.html', {'roles': CustomRole.objects.filter(**get_country_kwargs(request.user)), 'available_perms': AVAILABLE_PERMISSIONS})

@login_required
def delete_role(request, pk):
    if not (request.user.is_superuser or request.user.role in ['OWNER', 'COUNTRY_ADMIN']): return redirect('home')
    CustomRole.objects.filter(pk=pk, **get_country_kwargs(request.user)).delete()
    messages.success(request, "تم حذف الدور.")
    return redirect('super_manage_roles')


# ==========================================
# 11. الدعم الفني، الشكاوى والإشعارات العامة
# ==========================================
@login_required
def send_broadcast(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        title = request.POST.get('title')
        message = request.POST.get('message')
        target = request.POST.get('target')
        link = request.POST.get('link') or None  
        specific_user_id = request.POST.get('specific_user_id') 
        
        # 1. إرسال لمستخدم محدد
        if target == 'SPECIFIC' and specific_user_id:
            try:
                user = User.objects.get(id=specific_user_id, **get_country_kwargs(request.user))
                Notification.objects.create(recipient=user, title=title, message=message, link=link)
                send_push_to_user(user, title, message)
                messages.success(request, f"تم إرسال الإشعار للمستخدم '{user.first_name}' بنجاح ✅")
            except User.DoesNotExist:
                messages.error(request, "لم يتم العثور على المستخدم المحدد (أو لا ينتمي لدولتك).")
                
        # 2. إرسال عام (مجموعة)
        else:
            users = User.objects.filter(is_active=True, **get_country_kwargs(request.user)) 
            if target == 'MERCHANTS': users = users.filter(role='MERCHANT')
            elif target == 'CUSTOMERS': users = users.filter(role='CUSTOMER')
            
            Notification.objects.bulk_create([Notification(recipient=u, title=title, message=message, link=link) for u in users])
            for u in users: send_push_to_user(u, title, message)
            messages.success(request, f"تم إرسال الإشعار لـ {users.count()} مستخدم بنجاح ✅")
            
        return redirect('supervisor_dashboard')
        
    all_users = User.objects.filter(is_superuser=False, **get_country_kwargs(request.user)).order_by('-date_joined')
    return render(request, 'supervisor/send_broadcast.html', {'all_users': all_users})

@login_required
def support_tickets(request):
    if not is_supervisor(request.user): return redirect('home')
    status = request.GET.get('status')
    tickets = SupportTicket.objects.filter(**get_country_kwargs(request.user, 'customer__')).order_by('-created_at')
    if status: tickets = tickets.filter(status=status)
    return render(request, 'supervisor/support_tickets.html', {'tickets': tickets})

@login_required
def support_ticket_detail(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    ticket = get_object_or_404(SupportTicket, pk=pk, **get_country_kwargs(request.user, 'customer__'))
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            TicketMessage.objects.create(ticket=ticket, sender=request.user, message=message, is_support_reply=True)
            ticket.status = 'IN_PROGRESS' 
            ticket.save()
            send_notification(ticket.customer, "رد جديد من الدعم 📩", f"تم الرد على تذكرتك رقم #{ticket.id}. اضغط للمشاهدة.")
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
    complaints = DeliveryComplaint.objects.filter(**get_country_kwargs(request.user, 'customer__')).order_by('-created_at')
    return render(request, 'supervisor/admin_complaints_list.html', {'complaints': complaints})

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

@login_required
def admin_resolve_complaint(request, complaint_id):
    if not is_supervisor(request.user): return redirect('home')
    complaint = get_object_or_404(DeliveryComplaint, id=complaint_id, **get_country_kwargs(request.user, 'customer__'))
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
                    platform_fees_to_deduct = Decimal(order.platform_fees) if order.platform_fees else Decimal(0)
                    refund_to_customer = max(Decimal(0), Decimal(order.final_total) - shipping_to_deduct - platform_fees_to_deduct)
                    if getattr(order, 'paymob_transaction_id', None) and refund_to_customer > 0:
                        is_success, paymob_msg = process_paymob_refund(order.paymob_transaction_id, float(refund_to_customer))
                        if is_success: messages.success(request, f"تم التسوية وإرجاع {refund_to_customer} للعميل.")
                        else: messages.error(request, f"فشل الإرجاع الآلي: {paymob_msg}")
                
                order.status = 'RETURNED'
                order.save()
                complaint.is_resolved = True
                complaint.admin_notes = admin_notes or 'تمت التسوية المالية كمرتجع.'
                complaint.save()
                
                send_notification(order.customer, "تسوية شكوى ⚖️", f"تمت تسوية شكواك المتعلقة بالطلب #{order.order_id} وإرجاع المبلغ.")
                send_push_to_user(order.customer, "تسوية شكوى ⚖️", f"تمت تسوية شكواك المتعلقة بالطلب #{order.order_id} وإرجاع المبلغ.")
                
            elif resolution_action == 'force_deliver':
                order.status, order.is_confirmed_by_customer, order.rejection_reason = 'DELIVERED', True, None
                order.save()
                complaint.is_resolved, complaint.admin_notes = True, admin_notes or 'تأكيد التسليم لصالح التاجر.'
                complaint.save()
                
                send_notification(order.customer, "تحديث الشكوى ⚠️", f"تم إغلاق الشكوى للطلب #{order.order_id} وتأكيد التسليم.")
                send_push_to_user(order.customer, "تحديث الشكوى ⚠️", f"تم إغلاق الشكوى للطلب #{order.order_id} وتأكيد التسليم.")
                messages.success(request, "تم إغلاق الشكوى وتأكيد التسليم بالقوة!")

    return redirect(request.META.get('HTTP_REFERER', 'admin_complaints_list'))

@login_required
def super_reviews_list(request):
    if not is_supervisor(request.user): return redirect('supervisor_dashboard')
    reviews = ProductReview.objects.filter(**get_country_kwargs(request.user, 'product__')).order_by('-created_at')
    q, merchant_id, rating = request.GET.get('q'), request.GET.get('merchant'), request.GET.get('rating')
    if q: reviews = reviews.filter(Q(product__name__icontains=q) | Q(user__first_name__icontains=q) | Q(comment__icontains=q))
    if merchant_id: reviews = reviews.filter(product__merchant_id=merchant_id)
    if rating: reviews = reviews.filter(rating=rating)
    return render(request, 'supervisor/admin_reviews_list.html', {'reviews': reviews, 'merchants': MerchantProfile.objects.filter(**get_country_kwargs(request.user, 'user__'))})

@login_required
def process_return_refund(request, return_id):
    if not is_supervisor(request.user): return redirect('home')
    return_req = get_object_or_404(ReturnRequest, id=return_id, **get_country_kwargs(request.user, 'customer__'))
    order, merchant_wallet = return_req.order, return_req.order.merchant.wallet

    if request.method == 'POST':
        action = request.POST.get('action') 
        with transaction.atomic():
            if action == 'refund' and return_req.status == 'APPROVED':
                old_tx = WalletTransaction.objects.filter(wallet=merchant_wallet, description__icontains=f"#{order.id}", transaction_type='SALE').first()
                if old_tx:
                    WalletTransaction.objects.create(wallet=merchant_wallet, amount=-old_tx.amount, transaction_type='REFUND', description=f"خصم مرتجع #{order.id}", balance_after=merchant_wallet.balance - old_tx.amount)
                    merchant_wallet.balance -= old_tx.amount
                    merchant_wallet.save()
                order.status, return_req.status = 'RETURNED', 'REFUNDED'
                order.save(); return_req.save()
                
                send_notification(order.customer, "تم استرداد المبلغ 💸", f"تمت تسوية المرتجع الخاص بك للطلب #{order.order_id}.")
                send_push_to_user(order.customer, "تم استرداد المبلغ 💸", f"تمت تسوية المرتجع الخاص بك للطلب #{order.order_id}.")
                messages.success(request, f"تمت تسوية المرتجع بنجاح.")
                
            elif action == 'approve':
                return_req.status = 'APPROVED'
                return_req.save()
                
                send_notification(order.customer, "قبول طلب المرتجع ✅", f"تم قبول طلب الاسترجاع الخاص بك للطلب #{order.order_id}.")
                send_push_to_user(order.customer, "قبول طلب المرتجع ✅", f"تم قبول طلب الاسترجاع الخاص بك للطلب #{order.order_id}.")
                messages.success(request, "تم قبول المرتجع.")
                
            elif action == 'reject':
                return_req.status = 'REJECTED'
                return_req.save()
                
                send_notification(order.customer, "رفض المرتجع ❌", f"عذراً، تم رفض طلب الاسترجاع للطلب #{order.order_id}.")
                send_push_to_user(order.customer, "رفض المرتجع ❌", f"عذراً، تم رفض طلب الاسترجاع للطلب #{order.order_id}.")
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
    active_offers = Offer.objects.filter(is_active=True, end_date__gt=timezone.now(), **get_country_kwargs(request.user, 'product__'))

    if request.method == 'POST':
        title = request.POST.get('title')
        custom_link = request.POST.get('custom_link')
        offer_id = request.POST.get('offer_id')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        is_active = request.POST.get('is_active') == 'on' 
        image = request.FILES.get('image')
        c = request.user.country if request.user.role != 'OWNER' else None

        try:
            selected_offer = Offer.objects.get(id=offer_id) if offer_id else None
            popup = PromoPopup(
                country=c, title=title, custom_link=custom_link, offer=selected_offer,
                start_time=start_time, end_time=end_time, is_active=is_active, image=image
            )
            popup.clean()
            popup.save()
            messages.success(request, "تم جدولة الإعلان المنبثق بنجاح! 🚀")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
        return redirect('super_manage_popups')

    popups = PromoPopup.objects.filter(**get_country_kwargs(request.user)).order_by('-is_active', '-start_time')
    return render(request, 'supervisor/manage_popups.html', {'popups': popups, 'active_offers': active_offers})

@login_required
def super_toggle_popup(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    popup = get_object_or_404(PromoPopup, pk=pk, **get_country_kwargs(request.user))
    if popup.is_active:
        popup.is_active = False
        popup.save()
        messages.success(request, "تم إيقاف الإعلان بنجاح.")
    return redirect('super_manage_popups')

@login_required
def super_delete_popup(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    popup = get_object_or_404(PromoPopup, pk=pk, **get_country_kwargs(request.user))
    popup.delete()
    messages.success(request, "تم حذف الإعلان نهائياً.")
    return redirect('super_manage_popups')

@login_required
def manage_countries(request):
    if request.user.role != 'OWNER' and not request.user.is_superuser:
        return redirect('supervisor_dashboard')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            Country.objects.create(
                name=request.POST.get('name'),
                code=request.POST.get('code').upper(),
                phone_code=request.POST.get('phone_code'),
                currency_name=request.POST.get('currency_name'),
                currency_symbol=request.POST.get('currency_symbol'),
                paymob_integration_id_card=request.POST.get('paymob_card', ''),
                paymob_integration_id_wallet=request.POST.get('paymob_wallet', ''),
                is_active=request.POST.get('is_active') == 'on'
            )
            messages.success(request, "تمت إضافة الدولة بنجاح 🌍")
        elif action == 'edit':
            country = get_object_or_404(Country, id=request.POST.get('country_id'))
            country.name = request.POST.get('name')
            country.code = request.POST.get('code').upper()
            country.phone_code = request.POST.get('phone_code')
            country.currency_name = request.POST.get('currency_name')
            country.currency_symbol = request.POST.get('currency_symbol')
            country.paymob_integration_id_card = request.POST.get('paymob_card', '')
            country.paymob_integration_id_wallet = request.POST.get('paymob_wallet', '')
            country.is_active = request.POST.get('is_active') == 'on'
            country.save()
            messages.success(request, "تم تحديث بيانات الدولة ✏️")
            
        return redirect('super_manage_countries')
        
    countries = Country.objects.all().order_by('-is_active', 'name')
    return render(request, 'supervisor/manage_countries.html', {'countries': countries})

@login_required
def delete_country(request, pk):
    if request.user.role != 'OWNER' and not request.user.is_superuser:
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
            country_id = request.POST.get('country_id')
            name = request.POST.get('name')
            country = get_object_or_404(Country, id=country_id)
            
            if request.user.role != 'OWNER' and not request.user.is_superuser:
                if country != request.user.country:
                    messages.error(request, "غير مصرح لك بإضافة محافظة لدولة أخرى.")
                    return redirect('super_manage_governorates')
                    
            Governorate.objects.create(country=country, name=name)
            messages.success(request, f"تمت إضافة محافظة '{name}' بنجاح 📍")
            
        elif action == 'edit':
            gov_id = request.POST.get('gov_id')
            name = request.POST.get('name')
            gov = get_object_or_404(Governorate, id=gov_id)
            
            if request.user.role != 'OWNER' and not request.user.is_superuser:
                if gov.country != request.user.country:
                    messages.error(request, "غير مصرح لك بتعديل هذه المحافظة.")
                    return redirect('super_manage_governorates')
                    
            gov.name = name
            gov.save()
            messages.success(request, "تم تحديث اسم المحافظة ✏️")
            
        return redirect('super_manage_governorates')

    if request.user.role == 'OWNER' or request.user.is_superuser:
        governorates = Governorate.objects.all().select_related('country').order_by('country__name', 'name')
        countries = Country.objects.filter(is_active=True)
    else:
        governorates = Governorate.objects.filter(country=request.user.country).order_by('name')
        countries = [request.user.country]

    return render(request, 'supervisor/manage_governorates.html', {
        'governorates': governorates,
        'countries': countries
    })

@login_required
def delete_governorate(request, pk):
    if not is_supervisor(request.user): 
        return redirect('home')
        
    gov = get_object_or_404(Governorate, pk=pk)
    
    if request.user.role != 'OWNER' and not request.user.is_superuser:
        if gov.country != request.user.country:
            messages.error(request, "غير مصرح لك بحذف هذه المحافظة.")
            return redirect('super_manage_governorates')
            
    try:
        gov.delete()
        messages.success(request, "تم حذف المحافظة بنجاح 🗑️")
    except ProtectedError:
        messages.error(request, "لا يمكن الحذف! هذه المحافظة مرتبطة بطلبات أو إعدادات شحن سابقة.")
        
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
                obj.title_en = request.POST.get('title_en')
                obj.content_en = request.POST.get('content_en')
                obj.save()
                
            elif model_name == 'AboutUs':
                obj = AboutUs.objects.get(id=item_id)
                obj.content_en = request.POST.get('content_en')
                obj.save()

            messages.success(request, "تم حفظ الترجمة بنجاح ✅")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {e}")
            
        return redirect('super_system_translations') # اسم الرابط بتاع الصفحة دي

    # جلب البيانات للعرض (فلترة حسب دولة المشرف لو محتاج)
    context = {
        'categories': Category.objects.all(),
        'governorates': Governorate.objects.filter(**get_country_kwargs(request.user)),
        'terms': TermsAndCondition.objects.filter(**get_country_kwargs(request.user)),
        'about_us': AboutUs.objects.filter(**get_country_kwargs(request.user))
    }
    return render(request, 'supervisor/translations.html', context)