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
@login_required
def merchant_onboarding(request):
    if request.user.role != 'MERCHANT': return redirect('home')
    # ... (نفس كود الفورم السابق لرفع الصور الناقصة) ...
    return render(request, 'account/merchant_onboarding.html')