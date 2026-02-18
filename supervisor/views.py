from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum,Q

# الموديلات
from accounts.models import User
from store.models import (
    Product, Order, MerchantProfile, DepositRequest, 
    WithdrawalRequest, Offer, Category
)

# دالة التحقق
def is_supervisor(user):
    return user.is_superuser or user.role in [User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3, User.Role.OWNER]
def is_supervisor(user):
    return user.is_superuser or user.role in [User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3, User.Role.OWNER]

@login_required
def supervisor_dashboard(request):
    if not is_supervisor(request.user):
        return redirect('home')
    
    # إحصائيات سريعة
    pending_orders = Order.objects.filter(status=Order.Status.PENDING).count()
    pending_products = Product.objects.filter(is_active=False).count()
    pending_deposits = DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count()
    
    return render(request, 'supervisor/dashboard.html', {
        'pending_orders': pending_orders,
        'pending_products': pending_products,
        'pending_deposits': pending_deposits
    })

# ==========================
# 1. إدارة المنتجات
# ==========================
@login_required
def pending_products(request):
    if not is_supervisor(request.user): return redirect('home')
    # المنتجات غير المفعلة
    products = Product.objects.filter(is_active=False).order_by('-created_at')
    return render(request, 'supervisor/pending_products.html', {'products': products})

@login_required
def product_review(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            commission = request.POST.get('commission')
            product.admin_commission = commission # تحديد العمولة
            product.is_active = True # تفعيل
            product.save()
            messages.success(request, f"تم اعتماد المنتج {product.name} وعمولته {commission} ج.م")
            
        elif action == 'reject':
            product.delete() # أو يمكن إضافة حقل is_rejected
            messages.error(request, "تم رفض المنتج وحذفه.")
            
        return redirect('super_pending_products')

    return render(request, 'supervisor/product_review.html', {'product': product})

# ==========================
# 2. إدارة التجار
# ==========================
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
    return redirect('pending_merchants')

# ==========================
# 3. عروض المنصة (Owner Offers)
# ==========================
@login_required
def create_platform_offer(request):
    if not is_supervisor(request.user): return redirect('home')
    
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        percentage = request.POST.get('percentage')
        days = int(request.POST.get('days'))
        
        product = get_object_or_404(Product, pk=product_id)
        
        Offer.objects.update_or_create(
            product=product,
            defaults={
                'discount_percentage': percentage,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=days),
                'is_active': True,
                'is_platform_offer': True # <--- هذا هو السحر (تعويض)
            }
        )
        messages.success(request, "تم إطلاق عرض المنصة! سيتم تعويض التاجر عن الفرق.")
        return redirect('supervisor_dashboard')

    # نرسل المنتجات المفعلة فقط للاختيار منها
    products = Product.objects.filter(is_active=True)
    return render(request, 'supervisor/create_offer.html', {'products': products})


@login_required
def all_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    
    # فلترة حسب الحالة (اختياري)
    status = request.GET.get('status')
    orders = Order.objects.all().order_by('-created_at')
    
    if status:
        orders = orders.filter(status=status)
        
    return render(request, 'supervisor/all_orders.html', {'orders': orders})



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
    deposit.save() # الـ Signal سيزيد الرصيد تلقائياً
    
    messages.success(request, f"تم قبول الإيداع بقيمة {deposit.amount} ج.م")
    return redirect('super_pending_deposits')


@login_required
def team_management(request):
    user = request.user
    # حماية: Lvl3 لا يدخل هنا
    if user.role == User.Role.ADMIN_LVL3 or not is_supervisor(user):
        return redirect('supervisor_dashboard')

    # جلب المشرفين الحاليين
    team = User.objects.filter(role__in=[User.Role.ADMIN_LVL2, User.Role.ADMIN_LVL3]).exclude(pk=user.pk)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email') # استقبال الإيميل
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        role = request.POST.get('role')
        
        # حماية: Lvl2 لا يمكنه تعيين Lvl2 (فقط Lvl3)
        if user.role == User.Role.ADMIN_LVL2 and role == User.Role.ADMIN_LVL2:
            messages.error(request, "غير مسموح لك بتعيين مشرف من نفس درجتك.")
            return redirect('super_team')

        # إنشاء المستخدم
        try:
            new_admin = User.objects.create_user(username=username, password=password, phone_primary=phone, email=email)
            new_admin.role = role
            new_admin.is_staff = True # ليدخل لوحة جانجو أيضاً
            new_admin.save()
            messages.success(request, "تم تعيين المشرف بنجاح ✅")
        except Exception as e:
            messages.error(request, f"خطأ: {e}")
            
        return redirect('super_team')

    return render(request, 'supervisor/team_management.html', {'team': team})



# قائمة المستخدمين
@login_required
def users_list(request):
    if not is_supervisor(request.user): return redirect('home')
    
    role_filter = request.GET.get('role')
    search_query = request.GET.get('q')
    
    users = User.objects.all().order_by('-date_joined')
    
    if role_filter:
        users = users.filter(role=role_filter)
    if search_query:
        users = users.filter(Q(username__icontains=search_query) | Q(phone_primary__icontains=search_query))

    return render(request, 'supervisor/users_list.html', {'users': users})

# تعديل مستخدم (أو حظره)
@login_required
def user_edit(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    
    user_obj = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        user_obj.first_name = request.POST.get('first_name')
        user_obj.last_name = request.POST.get('last_name')
        user_obj.phone_primary = request.POST.get('phone')
        user_obj.email = request.POST.get('email')
        user_obj.username = request.POST.get('username')
        user_obj.role = request.POST.get('role')
        user_obj.is_active = request.POST.get('is_active') == 'on'
        
        # تغيير الباسورد (إذا كتبه)
        new_pass = request.POST.get('password')
        if new_pass:
            user_obj.set_password(new_pass)
            
        user_obj.save()
        messages.success(request, "تم التحديث الشامل.")
        return redirect('super_users_list')
        
    return render(request, 'supervisor/user_edit.html', {'user_obj': user_obj})

# حذف مستخدم
@login_required
def user_delete(request, user_id):
    if not is_supervisor(request.user): return redirect('home')
    user_obj = get_object_or_404(User, pk=user_id)
    if user_obj.is_superuser:
        messages.error(request, "لا يمكن حذف السوبر أدمن.")
    else:
        user_obj.delete()
        messages.success(request, "تم حذف المستخدم.")
    return redirect('super_users_list')


# ... (استيراد Category) ...

@login_required
def manage_categories(request):
    if not is_supervisor(request.user): return redirect('home')
    
    if request.method == 'POST':
        # إضافة قسم جديد
        name = request.POST.get('name')
        image = request.FILES.get('image')
        if name:
            Category.objects.create(name=name, image=image)
            messages.success(request, "تم إضافة القسم.")
        return redirect('super_categories')

    categories = Category.objects.all()
    return render(request, 'supervisor/categories.html', {'categories': categories})

@login_required
def delete_category(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    Category.objects.filter(pk=pk).delete()
    messages.success(request, "تم حذف القسم.")
    return redirect('super_categories')


from store.models import SiteSetting

@login_required
def site_settings_view(request):
    if not is_supervisor(request.user): return redirect('home')
    
    settings_obj = SiteSetting.objects.first()
    if not settings_obj:
        settings_obj = SiteSetting.objects.create()

    if request.method == 'POST':
        settings_obj.site_name = request.POST.get('site_name')
        settings_obj.platform_fee_fixed = request.POST.get('fee_fixed')
        settings_obj.platform_fee_percentage = request.POST.get('fee_percent')
        if request.FILES.get('banner'):
            settings_obj.banner_image = request.FILES.get('banner')
        
        settings_obj.save()
        messages.success(request, "تم حفظ الإعدادات.")
        return redirect('super_site_settings')

    return render(request, 'supervisor/site_settings.html', {'settings': settings_obj})


@login_required
def pending_withdrawals(request):
    if not is_supervisor(request.user): return redirect('home')
    withdrawals = WithdrawalRequest.objects.all().order_by('-created_at')
    return render(request, 'supervisor/pending_withdrawals.html', {'withdrawals': withdrawals})

@login_required
def approve_withdrawal(request, pk):
    if not is_supervisor(request.user): return redirect('home')
    
    # جلب الطلب
    withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
    
    if withdrawal.status == 'PENDING':
        # 1. تحديث حالة الطلب
        withdrawal.status = 'APPROVED'
        withdrawal.save()
        
        # 2. تحديث سجل المعاملة المالية (لجعلها نهائية)
        # نبحث عن المعاملة المرتبطة بهذا السحب (التي كانت بالسالب وقيد الانتظار)
        # (للتبسيط، سنبحث بآخر معاملة سحب معلقة لهذا التاجر، أو الأفضل إضافة حقل withdrawal_request في Transaction)
        
        # هنا سنفترض أننا نريد فقط تأكيد العملية إدارياً
        messages.success(request, f"تم تأكيد تحويل {withdrawal.amount} ج.م للتاجر {withdrawal.merchant.user.first_name}.")
        
    return redirect('super_pending_withdrawals')


@login_required
def order_detail(request, order_id):
    if not is_supervisor(request.user): return redirect('home')
    order = get_object_or_404(Order, order_id=order_id)
    return render(request, 'supervisor/order_detail.html', {'order': order})



import csv
from django.http import HttpResponse

@login_required
def export_orders(request):
    if not is_supervisor(request.user): return redirect('home')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'
    
    # BOM لدعم العربي في Excel
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response)
    writer.writerow(['رقم الطلب', 'العميل', 'الهاتف', 'الإجمالي', 'الحالة', 'التاريخ'])

    orders = Order.objects.all().values_list('order_id', 'customer__first_name', 'shipping_phone', 'final_total', 'status', 'created_at')
    
    for order in orders:
        writer.writerow(order)

    return response