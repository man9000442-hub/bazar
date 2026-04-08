from django import forms
from django.utils.translation import gettext_lazy as _
from .models import User
from store.models import MerchantProfile
# افترض أن موديل Country موجود في تطبيق supervisor، قم بتعديل المسار إذا كان مختلفاً
from accounts.models import Country 

# 1. Customer Form
class CustomerSignupForm(forms.ModelForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم مستخدم مميز')}),
        label=_("اسم المستخدم (Username)")
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}), 
        label=_("كلمة المرور")
    )
    
    class Meta:
        model = User
        # أضفنا حقل country هنا ليرتبط بالعميل مباشرة
        fields = ['first_name', 'last_name', 'username', 'phone_primary', 'country']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('01xxxxxxxxx')}),
            'country': forms.Select(attrs={'class': 'form-select fw-bold'}), # حقل اختيار الدولة
        }
        labels = {
            'phone_primary': _('رقم الموبايل'),
            'country': _('الدولة'),
            'first_name': _('الاسم الأول'),
            'last_name': _('اسم العائلة'),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(_("اسم المستخدم هذا مسجل مسبقاً، جرب اسماً آخر."))
        return username

    def clean_phone_primary(self):
        phone = self.cleaned_data.get('phone_primary')
        if User.objects.filter(phone_primary=phone).exists():
            raise forms.ValidationError(_("رقم الهاتف هذا مسجل بالفعل."))
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = User.Role.CUSTOMER
        if commit: 
            user.save()
        return user


# 2. Merchant Form (المحدث للعالمية)
class MerchantSignupForm(forms.ModelForm):
    # User Data
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("الاسم الأول"))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("اسم العائلة"))
    phone_primary = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("رقم الهاتف"))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password'}), label=_("كلمة المرور"))
    
    # حقل الدولة للتاجر (يتم تمريره للـ User لاحقاً)
    country = forms.ModelChoiceField(
        queryset=Country.objects.all(), # يمكنك إضافة .filter(is_active=True) لو عندك دول غير مفعلة
        widget=forms.Select(attrs={'class': 'form-select fw-bold'}),
        label=_("دولة المتجر (أين تبيع؟)")
    )
    
    # Merchant Data
    national_id = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("الرقم القومي / الهوية"))
    tax_register_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("رقم السجل الضريبي (اختياري)"))
    
    # تفاصيل البضاعة
    goods_quantity = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("كمية البضاعة (تقريباً)"))
    goods_types = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_("أنواع البضاعة"))
    goods_average_price = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("متوسط الأسعار"))
    goods_sizes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_("المقاسات المتاحة"))

    # الصور
    id_card_front = forms.ImageField(label=_("صورة البطاقة / الهوية (أمام)"))
    id_card_back = forms.ImageField(label=_("صورة البطاقة / الهوية (خلف)"))
    shop_image = forms.ImageField(label=_("صورة المحل / اللوجو"))

    class Meta:
        model = MerchantProfile
        fields = [
            'national_id', 'tax_register_number', 
            'goods_quantity', 'goods_types', 'goods_average_price', 'goods_sizes',
            'id_card_front', 'id_card_back', 'shop_image'
        ]

    def save(self, commit=True):
        # هنا قمنا بإضافة الدولة (country) أثناء إنشاء حساب التاجر
        user = User.objects.create_user(
            username=self.cleaned_data['phone_primary'],
            password=self.cleaned_data['password'],
            phone_primary=self.cleaned_data['phone_primary'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            country=self.cleaned_data['country'], # <-- ربط التاجر بدولته
            role=User.Role.MERCHANT
        )
        
        merchant = super().save(commit=False)
        merchant.user = user
        merchant.is_approved = False
        if commit: 
            merchant.save()
        return user


# 3. Google Complete Profile Form
class GoogleCompleteProfileForm(forms.ModelForm):
    is_merchant = forms.BooleanField(
        required=False, 
        label=_("أريد التسجيل كتاجر"), 
        widget=forms.CheckboxInput(attrs={'onchange': 'toggleMerchantFields()'})
    )
    
    # حقول التاجر الإضافية
    tax_register_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("رقم السجل الضريبي"))
    goods_quantity = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("كمية البضاعة"))
    goods_types = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_("أنواع البضاعة"))
    
    class Meta:
        model = User
        # أضفنا حقل country هنا أيضاً لكي يختاره القادم من جوجل
        fields = ['first_name', 'last_name', 'phone_primary', 'country']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('01xxxxxxxxx')}),
            'country': forms.Select(attrs={'class': 'form-select fw-bold'}),
        }
        labels = {
            'first_name': _('الاسم الأول'),
            'last_name': _('اسم العائلة'),
            'phone_primary': _('رقم الموبايل'),
            'country': _('دولتك'),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.username: 
            user.username = self.cleaned_data['phone_primary']
        
        if self.cleaned_data.get('is_merchant'):
            user.role = User.Role.MERCHANT
        else:
            user.role = User.Role.CUSTOMER
            
        if commit:
            user.save()
            if user.role == User.Role.MERCHANT:
                MerchantProfile.objects.create(
                    user=user,
                    tax_register_number=self.cleaned_data.get('tax_register_number'),
                    goods_quantity=self.cleaned_data.get('goods_quantity'),
                    goods_types=self.cleaned_data.get('goods_types'),
                )
        return user