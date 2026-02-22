from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from .forms import CustomerSignupForm, MerchantSignupForm, GoogleCompleteProfileForm
from django.contrib.auth.decorators import login_required


@login_required
def profile_view(request):
    return render(request, 'account/profile.html')

def signup_choice(request):
    if request.user.is_authenticated: return redirect('home')
    return render(request, 'account/signup_choice.html')

def customer_signup(request):
    if request.user.is_authenticated: return redirect('home')
    
    if request.method == 'POST':
        form = CustomerSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('home')
    else:
        form = CustomerSignupForm()
    return render(request, 'account/signup_customer.html', {'form': form})

def merchant_signup(request):
    if request.user.is_authenticated: return redirect('home')

    if request.method == 'POST':
        form = MerchantSignupForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            messages.success(request, "تم تسجيل طلبك بنجاح! سيتم مراجعته وتفعيل حسابك قريباً.")
            return redirect('home') # أو صفحة انتظار
    else:
        form = MerchantSignupForm()
    return render(request, 'account/signup_merchant.html', {'form': form})

# إكمال بيانات جوجل
@login_required
def complete_profile(request):
    user = request.user
    if user.phone_primary: return redirect('home')

    if request.method == 'POST':
        form = GoogleCompleteProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            if user.role == 'MERCHANT':
                return redirect('merchant_onboarding') # إذا كان هناك خطوة ثانية للصور
            return redirect('home')
    else:
        form = GoogleCompleteProfileForm(instance=user)

    return render(request, 'account/complete_profile.html', {'form': form})

# صفحة رفع الصور لمن سجل بجوجل كتاجر
from store.models import MerchantProfile
from .forms import MerchantSignupForm
from .models import User # أو فورم مخصص لو أردت

@login_required
def merchant_onboarding(request):
    # 1. الحماية: فقط لمن اختار دور "تاجر"
    if request.user.role != User.Role.MERCHANT:
        return redirect('home')

    # 2. هل التاجر أكمل بياناته بالفعل؟ (لديه بروفايل)
    # نستخدم getattr لتجنب الخطأ لو البروفايل مش موجود
    if hasattr(request.user, 'merchant_profile'):
        # إذا كان لديه بروفايل ولكن غير مفعل، نعرض رسالة انتظار
        if not request.user.merchant_profile.is_approved:
            messages.info(request, "حسابك قيد المراجعة. سيتم تفعيله قريباً.")
            return redirect('home')
        return redirect('merchant_dashboard')

    # 3. معالجة الفورم
    if request.method == 'POST':
        # نستخدم فورم مخصص للإكمال، أو نفس فورم التسجيل لكن نربطه بالمستخدم الحالي
        # هنا سننشئ MerchantProfile يدوياً من البيانات المرسلة
        
        # استلام البيانات
        national_id = request.POST.get('national_id')
        shop_image = request.FILES.get('shop_image')
        id_front = request.FILES.get('id_card_front')
        id_back = request.FILES.get('id_card_back')
        
        # البيانات الجديدة
        tax_reg = request.FILES.get('tax_register') # أو نص حسب الموديل
        goods_qty = request.POST.get('goods_quantity')
        goods_types = request.POST.get('goods_types')
        goods_price = request.POST.get('goods_average_price')
        goods_sizes = request.POST.get('goods_sizes')

        if national_id and id_front and id_back:
            # إنشاء البروفايل
            MerchantProfile.objects.create(
                user=request.user,
                national_id=national_id,
                id_card_front=id_front,
                id_card_back=id_back,
                shop_image=shop_image,
                
                # الحقول الجديدة
                tax_register=tax_reg,
                goods_quantity=goods_qty,
                goods_types=goods_types,
                goods_average_price=goods_price,
                goods_sizes=goods_sizes,
                
                is_approved=False # ينتظر الموافقة
            )
            messages.success(request, "تم إرسال بياناتك بنجاح! بانتظار التفعيل.")
            return redirect('home')
        else:
            messages.error(request, "يرجى ملء البيانات المطلوبة ورفع صور البطاقة.")

    # 4. عرض الصفحة (GET)
    return render(request, 'account/merchant_onboarding.html')



def terms_view(request):
    return render(request, 'terms.html')