from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import CompleteProfileForm, MerchantOnboardingForm,MerchantProfile,MerchantSignupForm,MySocialSignupForm,CustomerSignupForm
from store.models import MerchantProfile

from django.contrib import messages

from django.contrib.auth import login
from .forms import UnifiedSignupForm

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UnifiedSignupForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            if user.role == 'MERCHANT':
                return redirect('merchant_onboarding') # لرفع البطاقة
            return redirect('home')
    else:
        form = UnifiedSignupForm()

    return render(request, 'account/signup_unified.html', {'form': form})
# 1. إكمال البيانات الأساسية واختيار الدور
@login_required
def complete_profile(request):
    user = request.user
    print(f"--- Debug: User {user.email} entering complete_profile ---")

    # 1. إذا كان طلب POST (المستخدم ضغط حفظ)
    if request.method == 'POST':
        form = CompleteProfileForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save() # حفظ البيانات
            print(f"--- Debug: Data saved. Role is {user.role} ---")
            
            # التوجيه حسب الدور
            if user.role == 'MERCHANT':
                print("--- Debug: Redirecting to merchant onboarding ---")
                return redirect('merchant_onboarding')
            else:
                print("--- Debug: Redirecting to home ---")
                return redirect('home')
        else:
            print(f"--- Debug: Form Errors: {form.errors} ---") # طباعة الأخطاء لو وجدت
    
    # 2. إذا كان طلب GET (فتح الصفحة)
    else:
        # فحص: هل البيانات مكتملة بالفعل؟
        if user.phone_primary and user.first_name:
            if user.role == 'MERCHANT' and not hasattr(user, 'merchant_profile'):
                return redirect('merchant_onboarding')
            return redirect('home')
            
        form = CompleteProfileForm(instance=user)

    return render(request, 'account/complete_profile.html', {'form': form})
# 2. صفحة رفع بيانات التاجر (KYC)
@login_required
def merchant_onboarding(request):
    # حماية: لا يدخل هنا إلا من اختار "تاجر"
    if request.user.role != 'MERCHANT':
        return redirect('home')

    if request.method == 'POST':
        form = MerchantOnboardingForm(request.POST, request.FILES) # FILES مهمة للصور
        if form.is_valid():
            merchant = form.save(commit=False)
            merchant.user = request.user # ربط البروفايل بالمستخدم
            merchant.save()
            return redirect('home') # تم بنجاح
    else:
        form = MerchantOnboardingForm()

    return render(request, 'account/merchant_onboarding.html', {'form': form})


@login_required
def profile_view(request):
    return render(request, 'account/profile.html')



def signup_choice(request):
    return render(request, 'account/signup_choice.html')

def customer_signup(request):
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
    if request.method == 'POST':
        form = MerchantSignupForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, "تم تسجيل حساب التاجر بنجاح! بانتظار التفعيل.")
            return redirect('merchant_dashboard') # أو صفحة انتظار
    else:
        form = MerchantSignupForm()
    return render(request, 'account/signup_merchant.html', {'form': form})