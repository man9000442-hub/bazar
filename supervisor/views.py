from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum, Q
import csv
from django.http import HttpResponse
from django.db.models.functions import TruncMonth
import json
from django.db import transaction
from decimal import Decimal
# الموديلات
from accounts.models import User,CustomRole
from store.models import (
    Product, Order, MerchantProfile, DepositRequest, 
    WithdrawalRequest, Offer, Category, SiteSetting
)

from store.models import Wallet,WalletTransaction,WithdrawalRequest
from datetime import datetime, timedelta
from django.utils.dateparse import parse_date
# دالة التحقق
def is_supervisor(user):
    return user.is_superuser or user.role in [User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3, User.Role.OWNER]

# --- 1. Dashboard ---
@login_required
def supervisor_dashboard(request):
    if not is_supervisor(request.user): return redirect('home')
    
    pending_orders = Order.objects.filter(status=Order.Status.PENDING).count()
    pending_products = Product.objects.filter(is_active=False).count()
    pending_deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count()
    
    return render(request, 'supervisor/dashboard.html', {
        'pending_orders': pending_orders,
        'pending_products': pending_products,
        'pending_deposits': pending_deposits
    })

# --- 2. Orders ---
@login_required
def all_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    
    status = request.GET.get('status')
    orders = Order.objects.exclude(status=Order.Status.CART).order_by('-created_at')
    
    if status:
        orders = orders.filter(status=status)
        
    return render(request, 'supervisor/all_orders.html', {'orders': orders})

@login_required
def order_detail(request, order_id):
    if not is_supervisor(request.user): return redirect('home')
    order = get_object_or_404(Order, order_id=order_id)
    return render(request, 'supervisor/order_detail.html', {'order': order})

@login_required
def export_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['رقم الطلب', 'العميل', 'الهاتف', 'الإجمالي', 'الحالة', 'التاريخ'])
    orders = Order.objects.exclude(status='CART').values_list('order_id', 'customer__first_name', 'shipping_phone', 'final_total', 'status', 'created_at')
    for order in orders: writer.writerow(order)
    return response

# --- 3. Products ---
@login_required
def pending_products(request):
    if not is_supervisor(request.user): return redirect('home')
    products = Product.objects.filter(is_active=False).order_by('-created_at')
    return render(request, 'supervisor/pending_products.html', {'products': products})

@login_required
def product_review(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            commission_pct = request.POST.get('commission')
            product.commission_pct = commission_pct # حفظ النسبة
            product.is_active = True
            product.save()
            messages.success(request, f"تم اعتماد المنتج {product.name}")
        elif action == 'reject':
            product.delete()
            messages.error(request, "تم رفض وحذف المنتج.")
        return redirect('super_pending_products')

    return render(request, 'supervisor/product_review.html', {'product': product})

# --- 4. Merchants ---
@login_required
def pending_merchants(request):
    if not is_supervisor(request.user): return redirect('home')
    merchants = MerchantProfile.objects.filter(is_approved=False)
    return render(request, 'supervisor/pending_merchants.html', {'merchants': merchants})

@login_required
def approve_merchant(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    merchant = get_object_or_404(MerchantProfile, pk=pk)
    merchant.is_approved = True
    merchant.save()
    messages.success(request, f"تم تفعيل التاجر {merchant.user.first_name}")
    return redirect('super_pending_merchants')

# --- 5. Users ---
@login_required
def users_list(request):
    if not is_supervisor(request.user): return redirect('home')
    role = request.GET.get('role')
    q = request.GET.get('q')
    users = User.objects.all().order_by('-date_joined')
    if role: users = users.filter(role=role)
    if q: users = users.filter(Q(username__icontains=q) | Q(phone_primary__icontains=q))
    return render(request, 'supervisor/users_list.html', {'users': users})

@login_required
def user_edit(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_obj = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.phone_primary = request.POST.get('phone')
        user_obj.role = request.POST.get('role')
        user_obj.is_active = request.POST.get('is_active') == 'on'
        user_obj.first_name = request.POST.get('first_name')
        if request.POST.get('password'): user_obj.set_password(request.POST.get('password'))
        user_obj.save()
        messages.success(request, "تم التحديث.")
        return redirect('super_users_list')
    return render(request, 'supervisor/user_edit.html', {'user_obj': user_obj})

@login_required
def user_delete(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_obj = get_object_or_404(User, pk=user_id)
    if not user_obj.is_superuser:
        user_obj.delete()
        messages.success(request, "تم الحذف.")
    return redirect('super_users_list')

# --- 6. Finance (Deposits & Withdrawals) ---
@login_required
def pending_deposits(request):
    if not is_supervisor(request.user): return redirect('home')
    deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).order_by('-created_at')
    return render(request, 'supervisor/pending_deposits.html', {'deposits': deposits})

@login_required
def approve_deposit(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    deposit = get_object_or_404(DepositRequest, pk=pk)
    deposit.status = DepositRequest.Status.APPROVED
    deposit.save()
    messages.success(request, "تم قبول الإيداع.")
    return redirect('super_pending_deposits')

@login_required
def pending_withdrawals(request):
    if not is_supervisor(request.user): return redirect('home')
    # عرض الكل للتأكد، أو الفلتر
    withdrawals = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).order_by('-created_at')
    return render(request, 'supervisor/pending_withdrawals.html', {'withdrawals': withdrawals})

from store.models import Notification # تأكد من الاستيراد

@login_required
def approve_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    
    # جلب الطلب
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    
    if withdrawal.status == 'PENDING':
        # 1. تغيير الحالة
        withdrawal.status = 'APPROVED'
        withdrawal.save()
        
        # 2. تحديث سجل المعاملة (كما سبق)
        # (يمكنك البحث عن المعاملة وتغييرها لـ Released إذا أردت دقة 100%)
        
        # 3. إرسال إشعار للتاجر 🔔
        Notification.objects.create(
            recipient=withdrawal.merchant.user,
            title="تم تحويل الأرباح 💰",
            message=f"تمت الموافقة على طلب السحب بقيمة {withdrawal.amount} ج.م وتم التحويل لمحفظتك.",
            link="/merchant/wallet/" # رابط يوجهه لصفحة المحفظة
        )
        
        messages.success(request, f"تم تأكيد التحويل للتاجر {withdrawal.merchant.user.first_name}.")
        
    return redirect('super_pending_withdrawals')

# --- 7. Settings & Categories ---
@login_required
def manage_categories(request):
    if not is_supervisor(request.user): return redirect('home')
    if request.method == 'POST':
        Category.objects.create(name=request.POST.get('name'), image=request.FILES.get('image'))
        return redirect('super_categories')
    categories = Category.objects.all()
    return render(request, 'supervisor/categories.html', {'categories': categories})

@login_required
def delete_category(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    Category.objects.filter(pk=pk).delete()
    return redirect('super_categories')

@login_required
def site_settings_view(request):
    if not is_supervisor(request.user): return redirect('home')
    
    settings_obj = SiteSetting.objects.first()
    if not settings_obj:
        settings_obj = SiteSetting.objects.create()

    if request.method == 'POST':
        # البيانات العامة
        settings_obj.site_name = request.POST.get('site_name')
        settings_obj.platform_fee_fixed = request.POST.get('fee_fixed')
        settings_obj.platform_fee_percentage = request.POST.get('fee_percent')
        
        # السياسات المالية (تأكد من الأسماء هنا!)
        # في الـ HTML اسميناها: min_withdrawal, reserved_balance, min_active
        settings_obj.min_withdrawal_amount = request.POST.get('min_withdrawal')
        settings_obj.min_wallet_balance = request.POST.get('reserved_balance')
        settings_obj.min_active_balance = request.POST.get('min_active')
            # قيم الدعوات
        settings_obj.referral_reward_amount = request.POST.get('ref_reward')
        settings_obj.referral_discount_limit_pct = request.POST.get('ref_limit')
        settings_obj.referral_grace_period_hours = request.POST.get('ref_grace')
        
        if request.FILES.get('banner'):
            settings_obj.banner_image = request.FILES.get('banner')
        
        settings_obj.save()
        messages.success(request, "تم حفظ الإعدادات بنجاح ✅")
        return redirect('super_site_settings')

    return render(request, 'supervisor/site_settings.html', {'settings': settings_obj})

# --- 8. Offers & Team ---
@login_required
def create_platform_offer(request):
    if not is_supervisor(request.user): return redirect('home')
    
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        percentage = request.POST.get('percentage')
        days = int(request.POST.get('days'))
        
        # استلام خيارات الشحن المجاني
        free_shipping = request.POST.get('free_shipping') == 'on'
        threshold = int(request.POST.get('threshold', 1))
        
        product = get_object_or_404(Product, pk=product_id)
        
        Offer.objects.update_or_create(
            product=product,
            defaults={
                'discount_percentage': percentage,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=days),
                'is_active': True,
                'is_platform_offer': True, # عرض منصة (تعويض)
                
                # إعدادات الشحن
                'free_shipping': free_shipping,
                'free_shipping_threshold': threshold
            }
        )
        messages.success(request, "تم إطلاق عرض المنصة (خصم + شحن) مع التعويض!")
        return redirect('supervisor_dashboard')

    products = Product.objects.filter(is_active=True)
    return render(request, 'supervisor/create_offer.html', {'products': products})

from accounts.models import CustomRole # تأكد من الاستيراد

@login_required
def team_management(request):
    # 1. الحماية: فقط المالك (Owner) والسوبر يوزر يمكنهم الدخول
    if request.user.role != 'OWNER' and not request.user.is_superuser:
        return redirect('supervisor_dashboard')

    # 2. جلب البيانات (المشرفين + الأدوار المتاحة)
    # نستبعد المستخدم الحالي (عشان ما يحذفش نفسه)
    team = User.objects.filter(role__in=[User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3]).exclude(pk=request.user.pk)
    
    custom_roles = CustomRole.objects.all() # الأدوار اللي أنشأناها

    # 3. معالجة الإضافة (POST)
    if request.method == 'POST':
        username = request.POST.get('username')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role_id = request.POST.get('custom_role') # ID الدور المختار
        
        # التحقق من البيانات
        if User.objects.filter(username=username).exists():
            messages.error(request, "اسم المستخدم موجود مسبقاً.")
        elif User.objects.filter(phone_primary=phone).exists():
            messages.error(request, "رقم الهاتف مسجل بالفعل.")
        else:
            try:
                # إنشاء المستخدم
                new_admin = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    phone_primary=phone
                )
                
                # تعيين الصلاحيات
                new_admin.is_staff = True # ليدخل لوحة جانجو أيضاً (اختياري)
                
                # نربطه بالدور المخصص
                if role_id:
                    role_obj = CustomRole.objects.get(id=role_id)
                    new_admin.custom_role = role_obj
                    # نجعله "مشرف عام" كنوع أساسي، والتفاصيل في custom_role
                    new_admin.role = User.Role.ADMIN_LVL3 
                else:
                    # لو لم يختر دوراً، نجعله Lvl3 افتراضياً
                    new_admin.role = User.Role.ADMIN_LVL3

                new_admin.save()
                messages.success(request, f"تم تعيين المشرف {username} بنجاح ✅")
                
            except Exception as e:
                messages.error(request, f"حدث خطأ: {e}")
            
        return redirect('super_team')

    return render(request, 'supervisor/team_management.html', {
        'team': team,
        'custom_roles': custom_roles
    })


from django.db.models.functions import TruncDay, TruncMonth
from django.db.models import Sum, Q
import json
from datetime import timedelta
from django.utils.dateparse import parse_date

@login_required
def finance_overview(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # --- 1. تحديد النطاق الزمني ---
    range_type = request.GET.get('range', 'month') # الافتراضي: هذا الشهر
    custom_start = request.GET.get('start')
    custom_end = request.GET.get('end')
    
    today = timezone.now().date()
    # قيم افتراضية
    start_date = today.replace(day=1) 
    end_date = today

    if range_type == 'today':
        start_date = today
    elif range_type == 'week':
        start_date = today - timedelta(days=7)
    elif range_type == 'month':
        start_date = today.replace(day=1)
    elif range_type == 'year':
        start_date = today.replace(month=1, day=1)
    elif range_type == 'custom' and custom_start and custom_end:
        try:
            start_date = parse_date(custom_start)
            end_date = parse_date(custom_end)
        except:
            pass # في حالة الخطأ، نعود للافتراضي

    # --- 2. فلترة البيانات (QuerySet الأساسي) ---
    # نستخدم created_at__date__range لتغطية اليوم بالكامل
    base_qs = WalletTransaction.objects.filter(
        created_at__date__range=[start_date, end_date]
    )

    # --- 3. الحسابات المالية (KPIs) ---
    
    # أ. الدخل (Income): العمولات (SALE بالسالب)
    # ملاحظة: في signals.py سجلنا العمولة كـ SALE سالب.
    # نستخدم abs() لتحويلها لموجب للعرض
    income_val = base_qs.filter(
        amount__lt=0, 
        description__contains="خصم عمولة"
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    income = abs(float(income_val))

    # ب. المصروفات (Expenses): التعويضات (COMPENSATION)
    expenses_val = base_qs.filter(
        transaction_type=WalletTransaction.TxType.COMPENSATION
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    expenses = float(expenses_val)

    # ج. صافي الربح
    net_profit = income - expenses

    # د. التزامات التجار (Balance)
    # هذا الرقم تراكمي ولا يعتمد على التاريخ (نحسب الرصيد الحالي للكل)
    merchants_val = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0
    total_merchants_balance = float(merchants_val)

    # --- 4. تجهيز الشارت (Chart Data) ---
    
    # نحدد طريقة التجميع (يومياً أم شهرياً)
    trunc_func = TruncMonth if range_type == 'year' else TruncDay
    date_format = "%b %Y" if range_type == 'year' else "%d %b"

    # تجميع الإيرادات (الدخل فقط)
    chart_qs = base_qs.filter(
        amount__lt=0, 
        description__contains="خصم عمولة"
    ).annotate(period=trunc_func('created_at')).values('period').annotate(total=Sum('amount')).order_by('period')

    labels = []
    values = []

    # تحويل البيانات لقوائم
    for item in chart_qs:
        labels.append(item['period'].strftime(date_format))
        # نأخذ القيمة المطلقة لأنها مخزنة بالسالب
        values.append(abs(float(item['total'])))

    # إذا لم توجد بيانات، نضع قيماً فارغة لكي لا ينهار الشارت
    if not labels:
        labels = ["لا توجد بيانات"]
        values = [0]

    # --- 5. الإرسال للقالب ---
    context = {
        'income': income,
        'expenses': expenses,
        'net_profit': net_profit,
        'total_merchants_balance': total_merchants_balance,
        
        # بيانات الشارت (JSON)
        'chart_labels': json.dumps(labels),
        'chart_values': json.dumps(values),
        
        # بيانات الفلتر (لإعادة عرضها في الفورم)
        'current_range': range_type,
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'supervisor/finance_overview.html', context)

@login_required
def finance_logs(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # فلترة
    tx_type = request.GET.get('type')
    logs = WalletTransaction.objects.all().select_related('wallet__merchant__user').order_by('-created_at')
    
    if tx_type:
        logs = logs.filter(transaction_type=tx_type)
        
    return render(request, 'supervisor/finance_logs.html', {'logs': logs})



import csv
from django.http import HttpResponse

# تقرير الأرباح (كل العمليات)
@login_required
def export_profit_report(request):
    if not is_supervisor(request.user): return redirect('home')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="profits_report.csv"'
    response.write(u'\ufeff'.encode('utf8')) # BOM للعربي

    writer = csv.writer(response)
    writer.writerow(['المعرف', 'التاجر', 'النوع', 'المبلغ', 'الوصف', 'التاريخ'])

    # نأخذ كل المعاملات (أو يمكن فلترتها حسب التاريخ)
    transactions = WalletTransaction.objects.all().order_by('-created_at')
    
    for tx in transactions:
        writer.writerow([
            tx.id, 
            tx.wallet.merchant.user.first_name, 
            tx.get_transaction_type_display(), 
            tx.amount, 
            tx.description, 
            tx.created_at.strftime("%Y-%m-%d %H:%M")
        ])

    return response

# تقرير المديونيات (أرصدة التجار الحالية)
@login_required
def export_debts_report(request):
    if not is_supervisor(request.user): return redirect('home')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="merchants_balances.csv"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['التاجر', 'رقم الهاتف', 'الرصيد المتاح', 'الرصيد المعلق'])

    wallets = Wallet.objects.all()
    
    for w in wallets:
        writer.writerow([
            w.merchant.user.first_name,
            w.merchant.user.phone_primary,
            w.balance,
            w.pending_balance
        ])

    return response


@login_required
def reject_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    
    req = get_object_or_404(WithdrawalRequest, pk=pk)
    
    if req.status == 'PENDING':
        # 1. تغيير حالة الطلب
        req.status = 'REJECTED'
        req.save()
        
        # 2. إعادة المبلغ للمحفظة
        wallet = req.merchant.wallet
        wallet.balance += req.amount
        wallet.save()
        
        # 3. تسجيل حركة "استرداد" (Refund)
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=req.amount,
            transaction_type=WalletTransaction.TxType.COMPENSATION, # أو REFUND
            description=f"استرداد طلب سحب مرفوض #{req.id}",
            balance_after=wallet.balance,
            is_released=True
        )
        
        messages.warning(request, f"تم رفض السحب وإعادة {req.amount} ج.م للتاجر.")
        
    return redirect('super_pending_withdrawals')


from store.models import Wallet

@login_required
def wallets_list(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # التأكد من أن كل تاجر لديه محفظة
    for m in MerchantProfile.objects.all():
        Wallet.objects.get_or_create(merchant=m)
    
    wallets = Wallet.objects.all().order_by('-balance')
    return render(request, 'supervisor/wallets_list.html', {'wallets': wallets})

@login_required
def adjust_wallet(request, wallet_id):
    if not is_supervisor(request.user): return redirect('home')
    
    wallet = get_object_or_404(Wallet, pk=wallet_id)
    
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount'))
        reason = request.POST.get('reason')
        action = request.POST.get('action') # add or deduct
        
        with transaction.atomic():
            if action == 'add':
                wallet.balance += amount
                desc = f"إضافة إدارية: {reason}"
            else:
                wallet.balance -= amount
                desc = f"خصم إداري: {reason}"
            
            wallet.save()
            
            # تسجيل الحركة
            WalletTransaction.objects.create(
                wallet=wallet, amount=amount if action=='add' else -amount,
                transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=desc, balance_after=wallet.balance, is_released=True
            )
            messages.success(request, "تم تعديل الرصيد بنجاح.")
            return redirect('super_wallets_list')

    return render(request, 'supervisor/adjust_wallet.html', {'wallet': wallet})



from django.db.models import Count, Q

from django.db.models import F

@login_required
def all_products(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # 1. الاستعلام الأساسي (مع الحسابات)
    products = Product.objects.all().annotate(
        # عدد مرات البيع (عدد الـ OrderItems التي تم تسليمها)
        sales_count=Count('variations__orderitem', filter=Q(variations__orderitem__order__status='DELIVERED')),
        
        # إجمالي الإيرادات من هذا المنتج (اختياري، يحتاج Sum مع ExpressionWrapper معقد قليلاً، للتبسيط سنكتفي بالعدد)
        # revenue=Sum(F('variations__orderitem__quantity') * F('variations__orderitem__price_at_purchase'), ...)
    )

    # 2. الفلترة والترتيب
    q = request.GET.get('q')
    sort = request.GET.get('sort', '-created_at') # الافتراضي: الأحدث
    
    if q:
        products = products.filter(Q(name__icontains=q) | Q(merchant__user__first_name__icontains=q))
    
    if sort == 'best_selling':
        products = products.order_by('-sales_count')
    elif sort == 'price_high':
        products = products.order_by('-base_price')
    elif sort == 'price_low':
        products = products.order_by('base_price')
    else:
        products = products.order_by('-created_at')

    # 3. الإحصائيات العلوية (Top Stats)
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    # المنتج الأكثر مبيعاً (نجلبه من القائمة المرتبة)
    top_product = products.order_by('-sales_count').first()

    return render(request, 'supervisor/all_products.html', {
        'products': products,
        'total_count': total_products,
        'active_count': active_products,
        'top_product': top_product,
        'current_sort': sort
    })

# دالة الحذف (أدمن)
@login_required
def delete_product_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(Product, pk=pk)
    product.delete() # حذف نهائي أو إخفاء حسب سياستك
    messages.success(request, "تم حذف المنتج.")
    return redirect('super_all_products')

# دالة التعديل (أدمن) - يمكننا استخدام نفس قالب التاجر أو إنشاء واحد جديد
# للأدمن، يهمنا تعديل "الحالة" و "العمولة" أكثر من الوصف
@login_required
def edit_product_admin(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.is_active = request.POST.get('is_active') == 'on'
        product.commission_pct = request.POST.get('commission')
        product.save()
        messages.success(request, "تم تحديث المنتج.")
        return redirect('super_all_products')
        
    return render(request, 'supervisor/product_edit_admin.html', {'product': product})




from support.models import SupportTicket, TicketMessage

# 1. قائمة التذاكر
@login_required
def support_tickets(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # فلتر الحالة
    status = request.GET.get('status')
    tickets = SupportTicket.objects.all().order_by('-created_at')
    
    if status:
        tickets = tickets.filter(status=status)
        
    return render(request, 'supervisor/support_tickets.html', {'tickets': tickets})

# 2. صفحة الرد (Chat View)
@login_required
def support_ticket_detail(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    
    ticket = get_object_or_404(SupportTicket, pk=pk)
    
    if request.method == 'POST':
        # أ. الرد
        message = request.POST.get('message')
        if message:
            TicketMessage.objects.create(
                ticket=ticket, 
                sender=request.user, 
                message=message,
                is_support_reply=True
            )
            ticket.status = 'IN_PROGRESS' # تغيير الحالة تلقائياً
            ticket.save()
            messages.success(request, "تم إرسال الرد.")
        
        # ب. تغيير الحالة يدوياً (إغلاق التذكرة)
        new_status = request.POST.get('status')
        if new_status:
            ticket.status = new_status
            ticket.save()
            messages.info(request, "تم تحديث الحالة.")
            
        return redirect('super_ticket_detail', pk=pk)

    return render(request, 'supervisor/support_ticket_detail.html', {'ticket': ticket})



from accounts.models import CustomRole

# قائمة الصلاحيات المتاحة (للاختيار منها)
AVAILABLE_PERMISSIONS = [
    ('orders', 'إدارة الطلبات'),
    ('products', 'إدارة المنتجات'),
    ('categories', 'إدارة الأقسام'),
    ('users', 'إدارة المستخدمين'),
    ('merchants', 'تفعيل التجار'),
    ('finance', 'المالية والسحوبات'),
    ('settings', 'إعدادات الموقع'),
    ('support', 'الدعم الفني'),
    ('team', 'فريق العمل'),
    ('offers', 'إدارة العروض'),
    ('notifications', 'إرسال إشعارات'),
]

@login_required
def manage_roles(request):
    if request.user.role != 'OWNER' and not request.user.is_superuser:
        return redirect('supervisor_dashboard')
        
    roles = CustomRole.objects.all()
    
    if request.method == 'POST':
        name = request.POST.get('name')
        perms = request.POST.getlist('permissions') # استقبال القائمة
        perms_str = ",".join(perms) # تحويلها لنص
        
        CustomRole.objects.create(name=name, permissions=perms_str)
        messages.success(request, "تم إنشاء الدور بنجاح.")
        return redirect('super_manage_roles')

    return render(request, 'supervisor/manage_roles.html', {
        'roles': roles,
        'available_perms': AVAILABLE_PERMISSIONS
    })

@login_required
def delete_role(request, pk):
    if request.user.role != 'OWNER' and not request.user.is_superuser: return redirect('home')
    CustomRole.objects.filter(pk=pk).delete()
    messages.success(request, "تم حذف الدور.")
    return redirect('super_manage_roles')

# دالة التعديل والحذف بالمثل...



@login_required
def manage_offers(request):
    # التحقق من الصلاحية (offers)
    user = request.user
    if not (user.is_superuser or user.role == 'OWNER' or user.has_perm_access('offers')):
        return redirect('supervisor_dashboard')

    # جلب عروض المنصة فقط
    offers = Offer.objects.filter(is_platform_offer=True).order_by('-created_at')
    return render(request, 'supervisor/manage_offers.html', {'offers': offers})

@login_required
def delete_offer_admin(request, pk):
    # (نفس التحقق)
    Offer.objects.filter(pk=pk).delete()
    messages.success(request, "تم حذف العرض.")
    return redirect('super_manage_offers')


@login_required
def send_broadcast(request):
    # التحقق من الصلاحية (notifications)
    user = request.user
    if not (user.is_superuser or user.role == 'OWNER' or user.has_perm_access('notifications')):
        return redirect('supervisor_dashboard')

    if request.method == 'POST':
        title = request.POST.get('title')
        message = request.POST.get('message')
        target = request.POST.get('target') # ALL, MERCHANTS, CUSTOMERS
        
        users = User.objects.all()
        if target == 'MERCHANTS':
            users = users.filter(role='MERCHANT')
        elif target == 'CUSTOMERS':
            users = users.filter(role='CUSTOMER')
            
        # إرسال للكل (Bulk Create للأداء)
        notifs = [Notification(recipient=u, title=title, message=message) for u in users]
        Notification.objects.bulk_create(notifs)
        
        messages.success(request, f"تم إرسال الإشعار لـ {len(notifs)} مستخدم.")
        return redirect('supervisor_dashboard')

    return render(request, 'supervisor/send_broadcast.html')



from django.db.models.functions import TruncDay
from datetime import timedelta

@login_required
def supervisor_dashboard(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # 1. الإحصائيات العامة (Counters)
    pending_orders = Order.objects.filter(status=Order.Status.PENDING).count()
    pending_products = Product.objects.filter(is_active=False).count()
    pending_deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count()
    new_merchants = MerchantProfile.objects.filter(is_approved=False).count()

    # 2. المبيعات (Sales Stats)
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    
    # مبيعات اليوم
    sales_today = WalletTransaction.objects.filter(
        transaction_type='SALE', amount__gt=0, created_at__date=today
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # مبيعات الشهر
    sales_month = WalletTransaction.objects.filter(
        transaction_type='SALE', amount__gt=0, created_at__date__gte=start_of_month
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    # 3. الرسم البياني (آخر 7 أيام)
    last_7_days = today - timedelta(days=6)
    chart_data = WalletTransaction.objects.filter(
        transaction_type='SALE', amount__gt=0, created_at__date__gte=last_7_days
    ).annotate(day=TruncDay('created_at')).values('day').annotate(total=Sum('amount')).order_by('day')

    # تجهيز القوائم للرسم
    days_labels = []
    sales_values = []
    
    # نملأ الأيام الفارغة بـ 0 لضمان استمرار الرسم
    current_date = last_7_days
    data_dict = {entry['day'].date(): entry['total'] for entry in chart_data}
    
    for i in range(7):
        day_val = data_dict.get(current_date, 0)
        days_labels.append(current_date.strftime("%d %b")) # 15 Feb
        sales_values.append(float(day_val))
        current_date += timedelta(days=1)

    # 4. آخر 5 طلبات (للعرض السريع)
    recent_orders = Order.objects.all().select_related('customer').order_by('-created_at')[:5]

    context = {
        'pending_orders': pending_orders,
        'pending_products': pending_products,
        'pending_deposits': pending_deposits,
        'new_merchants': new_merchants,
        'sales_today': sales_today,
        'sales_month': sales_month,
        'chart_labels': json.dumps(days_labels),
        'chart_data': json.dumps(sales_values),
        'recent_orders': recent_orders,
    }
    
    return render(request, 'supervisor/dashboard.html', context)


@login_required
def banned_users(request):
    if not is_supervisor(request.user): return redirect('home')
    
    users = User.objects.filter(is_banned=True)
    return render(request, 'supervisor/banned_users.html', {'users': users})

@login_required
def ban_user(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user = get_object_or_404(User, pk=user_id)
    
    action = request.GET.get('action')
    if action == 'ban':
        user.is_banned = True
        messages.warning(request, f"تم حظر {user.username}")
    elif action == 'unban':
        user.is_banned = False
        messages.success(request, f"تم فك حظر {user.username}")
        
    user.save()
    return redirect('super_users_list') # أو banned_users