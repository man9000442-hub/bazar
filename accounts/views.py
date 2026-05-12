# ==========================================
# 1. الاستدعاءات الأساسية (Imports)
# ==========================================
import json
from django.shortcuts import render, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.forms import PasswordChangeForm
from django.utils.translation import gettext_lazy as _
from django.conf import settings

# النماذج (Forms) والموديلات
from .forms import CustomerSignupForm, MerchantSignupForm, GoogleCompleteProfileForm
from .models import User, UserFCMToken
from store.models import MerchantProfile, TermsAndCondition

# دوال الإشعارات (In-App & Push)
try:
    from store.utils import send_notification
except ImportError:
    def send_notification(user, title, message, link=None): pass

try:
    from store.utils import send_push_to_user 
except ImportError:
    def send_push_to_user(user, title, body): pass


# ==========================================
# 2. البروفايل الموحد والسياسات
# ==========================================
def profile_view(request):
    # 1. إعطاء قيم افتراضية (عشان الزوار غير المسجلين)
    user_type = 'CUSTOMER'
    user_country = None

    # 2. التأكد إن المستخدم مسجل دخول لتجنب أي إيرور (AnonymousUser)
    if request.user.is_authenticated:
        if getattr(request.user, 'role', None) == 'MERCHANT' or hasattr(request.user, 'merchantprofile'):
            user_type = 'MERCHANT'
        user_country = getattr(request.user, 'country', None)

    # 3. جلب السياسات المفعلة والمطابقة لنوع المستخدم
    active_policies = TermsAndCondition.objects.filter(is_active=True, user_type=user_type)

    # 4. الفلترة حسب الدولة بذكاء
    if user_country:
        active_policies = active_policies.filter(Q(country=user_country) | Q(country__isnull=True))
    else:
        active_policies = active_policies.filter(country__isnull=True)

    # 5. تجهيز البيانات للـ HTML 
    context = {
        'terms_policies': active_policies.filter(document_type='TERMS').order_by('order'),
        'privacy_policies': active_policies.filter(document_type='PRIVACY').order_by('order'),
        'shipping_policies': active_policies.filter(document_type='SHIPPING_RETURN').order_by('order'),
    }

    # 6. التوجيه بناءً على نوع الحساب
    if request.user.is_authenticated and getattr(request.user, 'role', None) == 'MERCHANT':
        return render(request, 'merchant/profile.html', context)
        
    return render(request, 'account/profile.html', context)


# ==========================================
# 3. التسجيل وتسجيل الدخول (العملاء والتجار)
# ==========================================
def signup_choice(request):
    """صفحة اختيار نوع الحساب (مشتري أو تاجر)"""
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'account/signup_choice.html')

def customer_signup(request):
    """تسجيل حساب عميل (مشتري) جديد مع حماية ضد التكرار"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        phone = request.POST.get('phone_primary') or request.POST.get('username') or request.POST.get('phone')
        email = request.POST.get('email')

        # التحقق من وجود الهاتف أو الإيميل مسبقاً لمنع خطأ 500
        if phone and User.objects.filter(Q(phone_primary=phone) | Q(username=phone)).exists():
            messages.error(request, "عفواً، رقم الهاتف مسجل بالفعل. يرجى تسجيل الدخول.")
            return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
            
        if email and User.objects.filter(email=email).exists():
            messages.error(request, "عفواً، البريد الإلكتروني مسجل بالفعل.")
            return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))

        try:
            form = CustomerSignupForm(request.POST)
            if form.is_valid():
                user = form.save()
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                
                send_notification(user=user, title="أهلاً بك في Elbazaar! 🎉", message="تم إنشاء حسابك بنجاح.", link="/")
                send_push_to_user(user=user, title="أهلاً بك في Elbazaar! 🎉", body="تم إنشاء حسابك بنجاح. استعد لأقوى العروض!")
                
                return redirect('home')
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{error}")
                return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
        except IntegrityError:
            messages.error(request, "حدث خطأ: البيانات مسجلة مسبقاً في النظام.")
            return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
    else:
        form = CustomerSignupForm()
        
    return render(request, 'account/signup_customer.html', {'form': form})

def merchant_signup(request):
    """تسجيل حساب تاجر جديد مع حماية قوية ضد التكرار والأخطاء"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        phone = request.POST.get('phone_primary') or request.POST.get('username') or request.POST.get('phone')

        # 1. التحقق من الموبايل
        if phone and User.objects.filter(Q(phone_primary=phone) | Q(username=phone)).exists():
            messages.error(request, "عفواً، رقم الهاتف مسجل بالفعل. يرجى تسجيل الدخول أو استخدام رقم آخر.")
            return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
            
        try:
            form = MerchantSignupForm(request.POST, request.FILES)
            if form.is_valid():
                user = form.save()
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                
                # الإشعارات
# الإشعارات
                try:
                    # 1. إشعار التاجر نفسه
                    send_notification(user=user, title="أهلاً بك كشريك نجاح! 🤝", message="تم تسجيل حسابك كتاجر. بياناتك قيد المراجعة.", link="/")
                    send_push_to_user(user=user, title="شريكنا الجديد! 🤝", body="تم تسجيل طلبك بنجاح، هنراجع متجرك ونفعله قريباً.")
                    
                    # 2. 🔥 إشعار لمدير الدولة والمالك (الجديد)
                    # نجلب المالك، أو أي مشرف ينتمي لنفس دولة التاجر
                    admins = User.objects.filter(
                        Q(role='OWNER') | 
                        (Q(role__in=['COUNTRY_ADMIN', 'ADMIN_LVL2', 'ADMIN_LVL3']) & Q(country=user.country))
                    )
                    
                    for admin in admins:
                        send_notification(
                            user=admin, 
                            title="طلب تسجيل تاجر جديد 🏪", 
                            message=f"التاجر '{user.first_name}' طلب الانضمام كبائع في {user.country.name}. يرجى مراجعة الطلب.", 
                            link="/supervisor/"  # يمكنك تغيير الرابط لصفحة إدارة التجار لاحقاً
                        )
                        send_push_to_user(
                            user=admin, 
                            title="طلب انضمام جديد 🏪", 
                            body=f"تاجر جديد من {user.country.name} ينتظر المراجعة والتفعيل."
                        )
                        
                except Exception as e:
                    pass # في حالة فشل الإشعارات لا نوقف عملية التسجيل # في حالة فشل الإشعارات لا نوقف التسجيل
                
                messages.success(request, "تم تسجيل طلبك بنجاح! سيتم مراجعته وتفعيل حسابك قريباً.")
                return redirect('home') 
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{error}")
                return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
                
        except IntegrityError as e:
            messages.error(request, f"حدث تعارض في البيانات (حقل مكرر): {str(e)}")
            return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
        except Exception as e:
            messages.error(request, f"خطأ في النظام: {str(e)} (تأكد من عمل Migrate)")
            return redirect(request.META.get('HTTP_REFERER', 'signup_choice'))
    else:
        form = MerchantSignupForm()
        
    # 🔥 التعديل هنا: نمرر متغير 'hide_popups' للواجهة
    context = {
        'form': form,
        'hide_popups': True  # هذا المتغير سيمنع ظهور أي نوافذ
    }
    return render(request, 'account/signup_merchant.html', context)


# ==========================================
# 4. إكمال البيانات ورفع الأوراق
# ==========================================
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
            send_notification(user=user, title="تم تحديث بياناتك ✅", message="شكراً لإكمال بيانات حسابك.", link="/profile/")
            send_push_to_user(user=user, title="اكتمل بروفايلك ✅", body="شكراً لتحديث بياناتك، حسابك دلوقتي جاهز 100%.")
            
            if user.role == 'MERCHANT': return redirect('merchant_onboarding')
            return redirect('home')
    else:
        form = GoogleCompleteProfileForm(instance=user)

    return render(request, 'account/complete_profile.html', {'form': form})

@login_required
def merchant_onboarding(request):
    """صفحة استكمال رفع الأوراق لمن سجل كتاجر عبر Google"""
    # التأكد من رتبة المستخدم
    if request.user.role != getattr(User.Role, 'MERCHANT', 'MERCHANT'):
        return redirect('home')

    # إذا كان لديه بروفايل بالفعل
    if hasattr(request.user, 'merchant_profile'):
        if not request.user.merchant_profile.is_approved:
            messages.info(request, "حسابك قيد المراجعة. سيتم تفعيله قريباً.")
            return redirect('home')
        return redirect('merchant_dashboard')

    if request.method == 'POST':
        # جلب البيانات من الفورم
        shop_image = request.FILES.get('shop_image')
        tax_reg_number = request.POST.get('tax_register') # رقم السجل الضريبي (نص)
        goods_qty = request.POST.get('goods_quantity')
        goods_types = request.POST.get('goods_types')
        goods_price = request.POST.get('goods_average_price')
        goods_sizes = request.POST.get('goods_sizes')

        # ملاحظة: تم استبعاد حقول البطاقة لأنها معطلة في الموديل حالياً
        if goods_types and goods_qty:
            try:
                MerchantProfile.objects.create(
                    user=request.user,
                    shop_image=shop_image,
                    tax_register_number=tax_reg_number, # الاسم الصحيح في الموديل
                    goods_quantity=goods_qty,           # الاسم الصحيح في الموديل
                    goods_types=goods_types,             # الاسم الصحيح في الموديل
                    goods_average_price=goods_price,     # الاسم الصحيح في الموديل
                    goods_sizes=goods_sizes,             # الاسم الصحيح في الموديل
                    is_approved=False 
                )
                
                # --- [إشعار الداتا بيز] ---
                send_notification(
                    user=request.user,
                    title="استلام أوراق المتجر 📁",
                    message="لقد استلمنا بيانات وصور متجرك بنجاح. حسابك الآن قيد المراجعة الإدارية للتفعيل.",
                    link="/"
                )

                # --- [إشعار الموبايل Push Notification] ---
                send_push_to_user(
                    user=request.user,
                    title="ورق متجرك وصلنا 📁",
                    body="استلمنا بياناتك وصورة متجرك، جارِ المراجعة والتفعيل."
                )
                
                messages.success(request, "تم إرسال بياناتك بنجاح! بانتظار التفعيل.")
                return redirect('home')
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
        else:
            messages.error(request, "يرجى ملء البيانات الأساسية المطلوبة.")

    return render(request, 'account/merchant_onboarding.html')


# ==========================================
# 5. التوجيه وإدارة إعدادات المستخدم
# ==========================================
def terms_view(request):
    terms = TermsAndCondition.objects.filter(is_active=True)
    return render(request, 'terms.html', {'terms': terms})

@login_required
def profile_router_view(request):
    role = getattr(request.user, 'role', '')
    if role == 'MERCHANT': return redirect('merchant_profile')
    elif role in ['OWNER', 'ADMIN_LVL2', 'ADMIN_LVL3']: return redirect('supervisor_dashboard')
    else: return redirect('customer_profile')

@login_required
def customer_profile_view(request):
    active_policies = TermsAndCondition.objects.filter(is_active=True, user_type='CUSTOMER').order_by('order')
    context = {
        'terms': active_policies.filter(document_type='TERMS'),
        'privacy': active_policies.filter(document_type='PRIVACY'),
        'shipping': active_policies.filter(document_type='SHIPPING_RETURN'),
    }
    return render(request, 'account/profile.html', context)

@login_required
def user_settings(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # تحديث البيانات الأساسية
        if action == 'update_info':
            user = request.user
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            
            new_phone = request.POST.get('phone')
            if new_phone:
                user.phone_primary = new_phone
                user.username = new_phone
                
            user.save()
            messages.success(request, _("تم تحديث بياناتك بنجاح ✅"))
            return redirect('user_settings')

        # تغيير كلمة المرور
        elif action == 'change_password':
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user) 
                messages.success(request, _("تم تغيير كلمة المرور بنجاح 🔒"))
            else:
                messages.error(request, _("خطأ في البيانات، يرجى التأكد من كلمة المرور الحالية."))
            return redirect('user_settings')

    return render(request, 'account/settings.html', {'languages': settings.LANGUAGES})

def redirect_to_login(request):
    if request.user.is_authenticated: return redirect('home') 
    return redirect('login')

def delete_account_request(request):
    return render(request, 'account/delete_account.html')


# ==========================================
# 6. البروفايل الخاص بالتاجر وإعداداته
# ==========================================
@login_required
def merchant_profile_view(request):
    if getattr(request.user, 'role', '') != 'MERCHANT': return redirect('profile_router') 
        
    merchant = request.user.merchant_profile
    current_country = request.user.country
    
    active_policies = TermsAndCondition.objects.filter(is_active=True, user_type='MERCHANT').filter(
        Q(country=current_country) | Q(country__isnull=True)
    ).order_by('order')
    
    context = {
        'merchant': merchant,
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
        if goods_qty and goods_qty.isdigit(): merchant.goods_quantity = goods_qty
            
        goods_price = request.POST.get('goods_average_price')
        if goods_price and goods_price.replace('.','',1).isdigit(): merchant.goods_average_price = goods_price
        
        if 'shop_image' in request.FILES: merchant.shop_image = request.FILES['shop_image']
            
        merchant.save()
        send_push_to_user(user=user, title="تحديث بيانات المتجر 🏪", body="تم حفظ التعديلات الجديدة على متجرك بنجاح.")
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
            send_push_to_user(user=request.user, title="تنبيه أمني 🔒", body="تم تغيير كلمة المرور بنجاح. إذا لم تكن أنت، تواصل مع الدعم فوراً.")
            messages.success(request, 'تم تغيير كلمة المرور بنجاح 🔒')
        else:
            messages.error(request, 'كلمة المرور الحالية غير صحيحة ❌')
            
    return redirect('merchant_profile')


# ==========================================
# 7. الإشعارات والـ FCM Token
# ==========================================
@login_required
def merchant_notifications_view(request):
    if getattr(request.user, 'role', '') != 'MERCHANT': return redirect('login')
    notifications = request.user.notifications.all().order_by('-created_at')
    return render(request, 'merchant/notifications.html', {'notifications': notifications})

@login_required
def mark_all_read(request):
    if request.method == 'POST':
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, 'تم تحديد جميع الإشعارات كمقروءة')
    return redirect('merchant_notifications')

@csrf_exempt
@login_required
def save_fcm_token(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            token = data.get('token')
            if token:
                UserFCMToken.objects.get_or_create(user=request.user, token=token)
                return JsonResponse({'status': 'success', 'message': 'Token saved perfectly'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalid method'}, status=400)