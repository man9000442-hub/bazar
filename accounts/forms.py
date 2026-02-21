from django import forms
from .models import User
from store.models import MerchantProfile

# 1. Customer Form
class CustomerSignupForm(forms.ModelForm):
    # إضافة حقل username يدوياً لنتحكم في الليبل والخصائص
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم مستخدم مميز'}),
        label="اسم المستخدم (Username)"
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}), 
        label="كلمة المرور"
    )
    
    class Meta:
        model = User
        # لاحظ: أضفنا username هنا
        fields = ['first_name', 'last_name', 'username', 'phone_primary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
        }
        labels = {
            'phone_primary': 'رقم الموبايل',
        }

    # التحقق المخصص (Validation)
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("اسم المستخدم هذا مسجل مسبقاً، جرب اسماً آخر.")
        return username

    def clean_phone_primary(self):
        phone = self.cleaned_data.get('phone_primary')
        if User.objects.filter(phone_primary=phone).exists():
            raise forms.ValidationError("رقم الهاتف هذا مسجل بالفعل.")
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        # لم نعد ننسخ الرقم للاسم، كل واحد منفصل
        user.role = User.Role.CUSTOMER
        if commit: user.save()
        return user

# 2. Merchant Form (المحدث)
class MerchantSignupForm(forms.ModelForm):
    # User Data
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="الاسم الأول")
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="اسم العائلة")
    phone_primary = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="رقم الهاتف")
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password'}), label="كلمة المرور")
    
    # Merchant Data
    national_id = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="الرقم القومي")
    tax_register_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label="رقم السجل الضريبي (اختياري)")
    
    # تفاصيل البضاعة
    goods_quantity = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="كمية البضاعة (تقريباً)")
    goods_types = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label="أنواع البضاعة")
    goods_average_price = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="متوسط الأسعار")
    goods_sizes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label="المقاسات المتاحة")

    # الصور
    id_card_front = forms.ImageField(label="صورة البطاقة (أمام)")
    id_card_back = forms.ImageField(label="صورة البطاقة (خلف)")
    shop_image = forms.ImageField(label="صورة المحل / اللوجو")

    class Meta:
        model = MerchantProfile
        fields = [
            'national_id', 'tax_register_number', 
            'goods_quantity', 'goods_types', 'goods_average_price', 'goods_sizes',
            'id_card_front', 'id_card_back', 'shop_image'
        ]

    def save(self, commit=True):
        user = User.objects.create_user(
            username=self.cleaned_data['phone_primary'],
            password=self.cleaned_data['password'],
            phone_primary=self.cleaned_data['phone_primary'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            role=User.Role.MERCHANT
        )
        
        merchant = super().save(commit=False)
        merchant.user = user
        merchant.is_approved = False
        if commit: merchant.save()
        return user

# 3. Google Complete (المحدث)
class GoogleCompleteProfileForm(forms.ModelForm):
    is_merchant = forms.BooleanField(required=False, label="أريد التسجيل كتاجر", widget=forms.CheckboxInput(attrs={'onchange': 'toggleMerchantFields()'}))
    
    # حقول التاجر الجديدة
    tax_register_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label="رقم السجل الضريبي")
    goods_quantity = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label="كمية البضاعة")
    goods_types = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), label="أنواع البضاعة")
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name','phone_primary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),

            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.username: user.username = self.cleaned_data['phone_primary']
        
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
                    # ... باقي الحقول ممكن نطلبها لاحقاً في التفعيل
                )
        return user