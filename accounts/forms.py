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


# 2. Merchant Form (المحدث للعالمية والمطابق لقاعدة البيانات)
# 2. Merchant Form (المحدث للعالمية والمطابق لقاعدة البيانات)
# 2. Merchant Form (المحدث لحذف اسم العائلة)
class MerchantSignupForm(forms.ModelForm):
    # User Data
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("الاسم بالكامل"))
    # ❌ تم حذف حقل last_name من هنا
    phone_primary = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_phone_primary'}), label=_("رقم الهاتف"))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password'}), label=_("كلمة المرور"))
    
    country = forms.ModelChoiceField(
        queryset=Country.objects.all(), 
        widget=forms.Select(attrs={'class': 'form-select fw-bold'}),
        label=_("دولة المتجر (أين تبيع؟)")
    )
    
    # Merchant Data
    tax_register_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("رقم السجل الضريبي (اختياري)"))
    
    # تفاصيل البضاعة 
    goods_quantity = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("كمية البضاعة (الكلية)"))
    goods_types = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label=_("أنواع البضاعة"))
    goods_average_price = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("متوسط الأسعار"))
    goods_sizes = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("المقاسات المتاحة"))
    
    expected_sales_quantity = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label=_("الكميات المتوقع بيعها (شهرياً)"))
    whatsapp_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_whatsapp_number'}), label=_("رقم الواتساب للتواصل"))

    shop_image = forms.ImageField(label=_("صورة المحل / اللوجو"))

    class Meta:
        model = MerchantProfile
        fields = [
            'tax_register_number', 
            'goods_quantity', 'goods_types', 'goods_average_price', 'goods_sizes', 
            'expected_sales_quantity', 'whatsapp_number', 
            'shop_image'
        ]

    def save(self, commit=True):
        from django.db import transaction
        import uuid
        
        with transaction.atomic():
            unique_email = f"m_{uuid.uuid4().hex[:6]}@elbazaare.com"
            
            # 1. إنشاء المستخدم (بدون اسم العائلة)
            user = User.objects.create_user(
                username=self.cleaned_data['phone_primary'],
                password=self.cleaned_data['password'],
                phone_primary=self.cleaned_data['phone_primary'],
                first_name=self.cleaned_data['first_name'],
                # ❌ حذفنا تمرير last_name هنا
                email=unique_email,
                country=self.cleaned_data['country'],
                role=User.Role.MERCHANT
            )
            
            # 2. ربط البيانات ببروفايل التاجر
            merchant = super().save(commit=False)
            merchant.user = user
            merchant.is_approved = False
            
            merchant.whatsapp_number = self.cleaned_data.get('whatsapp_number')
            merchant.expected_sales_quantity = self.cleaned_data.get('expected_sales_quantity')
            merchant.tax_register_number = self.cleaned_data.get('tax_register_number')
            merchant.goods_quantity = self.cleaned_data.get('goods_quantity')
            merchant.goods_types = self.cleaned_data.get('goods_types')
            merchant.goods_average_price = self.cleaned_data.get('goods_average_price')
            merchant.goods_sizes = self.cleaned_data.get('goods_sizes')

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