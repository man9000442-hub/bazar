from django.shortcuts import render, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required

# === استدعاء النماذج (Forms) والموديلات ===
from .forms import CustomerSignupForm, MerchantSignupForm, GoogleCompleteProfileForm
from .models import User
from store.models import MerchantProfile, TermsAndCondition

# === استدعاء دوال الإشعارات (In-App & Push) ===
try:
    # استدعاء إشعار الداتا بيز الداخلي
    from store.utils import send_notification
except ImportError:
    def send_notification(user, title, message, link=None):
        pass

try:
    # 🔥 استدعاء دالة الإشعارات للموبايل (Push Notifications) الجديدة
    from store.utils import send_push_to_user 
except ImportError:
    def send_push_to_user(user, title, body):
        pass  # حماية عشان لو الملف مش موجود السيرفر ميضربش


def profile_view(request):
    if request.user.is_authenticated and request.user.role == 'MERCHANT':
        return render(request, 'merchant/profile.html')
    # تحديد نوع المستخدم
    user_type = 'MERCHANT' if hasattr(request.user, 'merchantprofile') else 'CUSTOMER'
    
    active_policies = TermsAndCondition.objects.filter(is_active=True, user_type=user_type).order_by('order')
    
    context = {
        'terms': active_policies.filter(document_type='TERMS'),
        'privacy': active_policies.filter(document_type='PRIVACY'),
        'shipping': active_policies.filter(document_type='SHIPPING_RETURN'),
    }
    return render(request, 'account/profile.html', context)


def signup_choice(request):
    """صفحة اختيار نوع الحساب (مشتري أو تاجر)"""
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'account/signup_choice.html')


def customer_signup(request):
    """تسجيل حساب عميل (مشتري) جديد"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = CustomerSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            # --- [إشعار الداتا بيز] ---
            send_notification(
                user=user,
                title="أهلاً بك في Elbazaar! 🎉",
                message="تم إنشاء حسابك بنجاح. استمتع بتسوق أحدث المنتجات والعروض المميزة.",
                link="/"
            )
            
            # 🔥 --- [إشعار الموبايل Push Notification] ---
            send_push_to_user(
                user=user,
                title="أهلاً بك في Elbazaar! 🎉",
                body="تم إنشاء حسابك بنجاح. استعد لأقوى العروض!"
            )
            
            return redirect('home')
    else:
        form = CustomerSignupForm()
        
    return render(request, 'account/signup_customer.html', {'form': form})


def merchant_signup(request):
    """تسجيل حساب تاجر جديد"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = MerchantSignupForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            # --- [إشعار الداتا بيز] ---
            send_notification(
                user=user,
                title="أهلاً بك كشريك نجاح! 🤝",
                message="تم تسجيل حسابك كتاجر بنجاح. بياناتك الآن قيد المراجعة، وسنخبرك فور تفعيل متجرك.",
                link="/"
            )

            # 🔥 --- [إشعار الموبايل Push Notification] ---
            send_push_to_user(
                user=user,
                title="شريكنا الجديد! 🤝",
                body="تم تسجيل طلبك بنجاح، فريقنا هيراجع متجرك ويفعله في أقرب وقت."
            )
            
            messages.success(request, "تم تسجيل طلبك بنجاح! سيتم مراجعته وتفعيل حسابك قريباً.")
            return redirect('home') 
    else:
        form = MerchantSignupForm()
        
    return render(request, 'account/signup_merchant.html', {'form': form})


@login_required
def complete_profile(request):
    """إكمال بيانات المستخدم (لمن سجل الدخول عبر Google)"""
    user = request.user
    if user.phone_primary:
        return redirect('home')

    if request.method == 'POST':
        form = GoogleCompleteProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            
            # --- [إشعار الداتا بيز] ---
            send_notification(
                user=user,
                title="تم تحديث بياناتك ✅",
                message="شكراً لإكمال بيانات حسابك. نتمنى لك تجربة تسوق رائعة.",
                link="/profile/"
            )

            # 🔥 --- [إشعار الموبايل Push Notification] ---
            send_push_to_user(
                user=user,
                title="اكتمل بروفايلك ✅",
                body="شكراً لتحديث بياناتك، حسابك دلوقتي جاهز 100%."
            )
            
            if user.role == 'MERCHANT':
                return redirect('merchant_onboarding')
            return redirect('home')
    else:
        form = GoogleCompleteProfileForm(instance=user)

    return render(request, 'account/complete_profile.html', {'form': form})


@login_required
def merchant_onboarding(request):
    """صفحة استكمال رفع الأوراق لمن سجل كتاجر عبر Google"""
    if request.user.role != getattr(User.Role, 'MERCHANT', 'MERCHANT'):
        return redirect('home')

    if hasattr(request.user, 'merchant_profile'):
        if not request.user.merchant_profile.is_approved:
            messages.info(request, "حسابك قيد المراجعة. سيتم تفعيله قريباً.")
            return redirect('home')
        return redirect('merchant_dashboard')

    if request.method == 'POST':
        national_id = request.POST.get('national_id')
        shop_image = request.FILES.get('shop_image')
        id_front = request.FILES.get('id_card_front')
        id_back = request.FILES.get('id_card_back')
        
        tax_reg = request.FILES.get('tax_register') 
        goods_qty = request.POST.get('goods_quantity')
        goods_types = request.POST.get('goods_types')
        goods_price = request.POST.get('goods_average_price')
        goods_sizes = request.POST.get('goods_sizes')

        if national_id and id_front and id_back:
            MerchantProfile.objects.create(
                user=request.user,
                national_id=national_id,
                id_card_front=id_front,
                id_card_back=id_back,
                shop_image=shop_image,
                tax_register=tax_reg,
                goods_quantity=goods_qty,
                goods_types=goods_types,
                goods_average_price=goods_price,
                goods_sizes=goods_sizes,
                is_approved=False 
            )
            
            # --- [إشعار الداتا بيز] ---
            send_notification(
                user=request.user,
                title="استلام أوراق المتجر 📁",
                message="لقد استلمنا بيانات وصور متجرك بنجاح. حسابك الآن قيد المراجعة الإدارية للتفعيل.",
                link="/"
            )

            # 🔥 --- [إشعار الموبايل Push Notification] ---
            send_push_to_user(
                user=request.user,
                title="ورق متجرك وصلنا 📁",
                body="استلمنا بياناتك وصور البطاقة، جارِ المراجعة والتفعيل."
            )
            
            messages.success(request, "تم إرسال بياناتك بنجاح! بانتظار التفعيل.")
            return redirect('home')
        else:
            messages.error(request, "يرجى ملء البيانات المطلوبة ورفع صور البطاقة.")

    return render(request, 'account/merchant_onboarding.html')


def terms_view(request):
    """عرض صفحة الشروط والأحكام"""
    terms = TermsAndCondition.objects.filter(is_active=True)
    return render(request, 'terms.html', {'terms': terms})


@login_required
def profile_router_view(request):
    """دالة ذكية توجه المستخدم للبروفايل الصحيح بناءً على رتبته"""
    role = getattr(request.user, 'role', '')
    
    if role == 'MERCHANT':
        return redirect('merchant_profile')
    elif role in ['OWNER', 'ADMIN_LVL2', 'ADMIN_LVL3']:
        return redirect('supervisor_dashboard')
    else:
        return redirect('customer_profile')


@login_required
def customer_profile_view(request):
    active_policies = TermsAndCondition.objects.filter(is_active=True, user_type='CUSTOMER').order_by('order')
    
    context = {
        'terms': active_policies.filter(document_type='TERMS'),
        'privacy': active_policies.filter(document_type='PRIVACY'),
        'shipping': active_policies.filter(document_type='SHIPPING_RETURN'),
    }
    return render(request, 'account/profile.html', context)


from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from store.models import TermsAndCondition # تأكد من المسار حسب مشروعك

@login_required
def merchant_profile_view(request):
    # التأكد من أن المستخدم تاجر
    if getattr(request.user, 'role', '') != 'MERCHANT':
        return redirect('profile_router') 
        
    merchant = request.user.merchant_profile
    current_country = request.user.country
    
    # 🔥 الفلترة الذكية: نجيب سياسات التجار + المفعلة + (الخاصة بدولة التاجر أو العامة اللي بدون دولة)
    active_policies = TermsAndCondition.objects.filter(
        is_active=True, 
        user_type='MERCHANT'
    ).filter(
        Q(country=current_country) | Q(country__isnull=True)
    ).order_by('order')
    
    context = {
        'merchant': merchant,
        # 🔥 تم توحيد الأسماء لتتطابق مع الـ HTML الجديد
        'terms_list': active_policies.filter(document_type='TERMS'),
        'privacy_list': active_policies.filter(document_type='PRIVACY'),
        'shipping_list': active_policies.filter(document_type='SHIPPING_RETURN'),
    }
    return render(request, 'merchant/profile.html', context)

@login_required
def merchant_profile_update(request):
    if request.method == 'POST' and getattr(request.user, 'role', '') == 'MERCHANT':
        user = request.user
        merchant = user.merchant_profile
        
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        
        merchant.goods_types = request.POST.get('goods_types', merchant.goods_types)
        merchant.goods_sizes = request.POST.get('goods_sizes', merchant.goods_sizes)
        
        goods_qty = request.POST.get('goods_quantity')
        if goods_qty and goods_qty.isdigit():
            merchant.goods_quantity = goods_qty
            
        goods_price = request.POST.get('goods_average_price')
        if goods_price and goods_price.replace('.','',1).isdigit():
            merchant.goods_average_price = goods_price
        
        if 'shop_image' in request.FILES:
            merchant.shop_image = request.FILES['shop_image']
            
        merchant.save()

        # 🔥 --- [إشعار الموبايل Push Notification لتأكيد التعديل] ---
        send_push_to_user(
            user=user,
            title="تحديث بيانات المتجر 🏪",
            body="تم حفظ التعديلات الجديدة على بيانات متجرك بنجاح."
        )

        messages.success(request, 'تم حفظ بيانات المتجر بنجاح ✅')
        return redirect('merchant_profile') 
        
    return redirect('merchant_profile')


@login_required
def merchant_change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        
        if request.user.check_password(old_password):
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            
            # 🔥 --- [إشعار الموبايل Push Notification لتنبيه الأمان] ---
            send_push_to_user(
                user=request.user,
                title="تنبيه أمني 🔒",
                body="تم تغيير كلمة المرور الخاصة بحسابك بنجاح. إذا لم تكن أنت، تواصل مع الدعم فوراً."
            )

            messages.success(request, 'تم تغيير كلمة المرور بنجاح 🔒')
        else:
            messages.error(request, 'كلمة المرور الحالية غير صحيحة ❌')
            
    return redirect('merchant_profile')


@login_required
def merchant_notifications_view(request):
    if getattr(request.user, 'role', '') != 'MERCHANT':
        return redirect('login')
    
    notifications = request.user.notifications.all().order_by('-created_at')
    
    return render(request, 'merchant/notifications.html', {
        'notifications': notifications
    })


@login_required
def mark_all_read(request):
    if request.method == 'POST':
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, 'تم تحديد جميع الإشعارات كمقروءة')
    return redirect('merchant_notifications')


def redirect_to_login(request):
    """دالة بسيطة لتحويل المستخدم لصفحة تسجيل الدخول"""
    if request.user.is_authenticated:
        return redirect('home') 
    
    return redirect('login')


def delete_account_request(request):
    return render(request, 'account/delete_account.html')

import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import UserFCMToken
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required
def save_fcm_token(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            token = data.get('token')
            
            if token:
                # حفظ التوكن للعميل (لو موجود مش هيكرره)
                UserFCMToken.objects.get_or_create(user=request.user, token=token)
                return JsonResponse({'status': 'success', 'message': 'Token saved perfectly'})
        
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return JsonResponse({'status': 'invalid method'}, status=400)