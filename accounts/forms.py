from django import forms
from .models import User
from store.models import MerchantProfile # سنحتاج هذا لبيانات التاجر
from allauth.socialaccount.forms import SignupForm
# 1. الفورم الأساسي (للاختيار بين عميل وتاجر)


class MySocialSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # هنا يمكنك إضافة حقول إذا أردت، أو تركها فارغة لتجاوز الصفحة
        # إذا كنت تريد تجاوز الصفحة تماماً، يجب أن تكون الحقول الإجبارية (غير الموجودة في جوجل)
        # غير مطلوبة هنا، وسنطلبها لاحقاً في صفحة complete_profile.
        
    def save(self, request):
        # هذه الدالة تنفذ الحفظ.
        user = super().save(request)
        # يمكنك هنا تعيين قيم افتراضية
        user.role = 'CUSTOMER' # افتراضياً عميل حتى يغيرها
        user.save()
        return user
class CompleteProfileForm(forms.ModelForm):
    # نحدد الخيارات يدوياً لنخفي الأدمن والمشرفين
    ROLE_CHOICES = [
        ('CUSTOMER', 'عميل (أريد الشراء)'),
        ('MERCHANT', 'تاجر (أريد البيع)'),
    ]
    
    role = forms.ChoiceField(
        choices=ROLE_CHOICES, 
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}), # ستايل أزرار للاختيار
        label="أريد التسجيل كـ"
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_primary', 'phone_secondary', 'role']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الاسم الأول'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم العائلة'}),
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
            'phone_secondary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم احتياطي'}),
        }

# 2. فورم التاجر (يظهر فقط لمن اختار "تاجر")
class MerchantOnboardingForm(forms.ModelForm):
    class Meta:
        model = MerchantProfile
        fields = ['national_id', 'id_card_front', 'id_card_back', 'shop_image']
        widgets = {
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'الرقم القومي (14 رقم)'}),
            'id_card_front': forms.FileInput(attrs={'class': 'form-control'}),
            'id_card_back': forms.FileInput(attrs={'class': 'form-control'}),
            'shop_image': forms.FileInput(attrs={'class': 'form-control'}),
        }



from django import forms
from .models import User
from store.models import MerchantProfile

class UnifiedSignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'id_password'}), label="كلمة المرور")
    email = forms.EmailField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label="البريد الإلكتروني (اختياري)")
    
    # حقول التاجر
    is_merchant = forms.BooleanField(required=False, label="أريد التسجيل كتاجر", widget=forms.CheckboxInput(attrs={'onchange': 'toggleMerchantFields()'}))
    shop_description = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), label="وصف البضاعة (إجباري للتاجر)")
    tax_register = forms.FileField(required=False, label="السجل الضريبي (اختياري)")

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_primary']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_merchant = cleaned_data.get('is_merchant')
        shop_desc = cleaned_data.get('shop_description')

        if is_merchant and not shop_desc:
            self.add_error('shop_description', "وصف البضاعة مطلوب للتجار.")
        
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.username = self.cleaned_data['phone_primary'] # نستخدم الهاتف كاسم مستخدم
        
        if self.cleaned_data.get('email'):
            user.email = self.cleaned_data['email']
            
        if self.cleaned_data.get('is_merchant'):
            user.role = User.Role.MERCHANT
        else:
            user.role = User.Role.CUSTOMER
            
        if commit:
            user.save()
            # إنشاء بروفايل التاجر إذا لزم الأمر
            if user.role == User.Role.MERCHANT:
                MerchantProfile.objects.create(
                    user=user,
                    business_description=self.cleaned_data.get('shop_description'),
                    tax_register=self.cleaned_data.get('tax_register')
                    # ملاحظة: البطاقة الشخصية سنطلبها لاحقاً في خطوة التفعيل
                )
        return user
    

class GoogleCompleteProfileForm(forms.ModelForm):
    # تعريف الحقول الإضافية
    is_merchant = forms.BooleanField(
        required=False, 
        label="أريد التسجيل كتاجر", 
        widget=forms.CheckboxInput(attrs={'onchange': 'toggleMerchantFields()'})
    )
    
    shop_description = forms.CharField(
        required=False, 
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), 
        label="وصف البضاعة (إجباري للتاجر)"
    )
    
    tax_register = forms.FileField(
        required=False, 
        label="السجل الضريبي (اختياري)"
    )

    class Meta:
        model = User
        fields = ['phone_primary'] # نطلب الرقم فقط لأن الاسم موجود
        widgets = {
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_merchant = cleaned_data.get('is_merchant')
        shop_desc = cleaned_data.get('shop_description')

        if is_merchant and not shop_desc:
            self.add_error('shop_description', "وصف البضاعة مطلوب للتجار.")
        
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # تحديد الدور
        if self.cleaned_data.get('is_merchant'):
            user.role = User.Role.MERCHANT
        else:
            user.role = User.Role.CUSTOMER
            
        if commit:
            user.save()
            # إنشاء بروفايل التاجر
            if user.role == User.Role.MERCHANT:
                MerchantProfile.objects.create(
                    user=user,
                    business_description=self.cleaned_data.get('shop_description'),
                    tax_register=self.cleaned_data.get('tax_register')
                )
        return user
    

class CustomerSignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="كلمة المرور")
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_primary']
        widgets = {
            'phone_primary': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.username = self.cleaned_data['phone_primary']
        user.role = User.Role.CUSTOMER
        if commit: user.save()
        return user

# 2. فورم التاجر (الكامل)
class MerchantSignupForm(forms.ModelForm):
    # بيانات المستخدم
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="الاسم الأول")
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="اسم العائلة")
    phone_primary = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="رقم الهاتف")
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="كلمة المرور")
    
    # بيانات المتجر (من MerchantProfile)
    national_id = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}), label="الرقم القومي")
    id_card_front = forms.ImageField(label="صورة البطاقة (أمام)")
    id_card_back = forms.ImageField(label="صورة البطاقة (خلف)")
    shop_image = forms.ImageField(label="صورة المحل / اللوجو")
    tax_register = forms.FileField(required=False, label="السجل الضريبي (PDF/Image)")
    business_description = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), label="وصف النشاط")

    class Meta:
        model = MerchantProfile
        # لاحظ: نحن هنا نستخدم MerchantProfile كنموذج أساسي، لكننا نضيف حقول User يدوياً
        fields = ['national_id', 'id_card_front', 'id_card_back', 'shop_image', 'tax_register', 'business_description']

    def save(self, commit=True):
        # 1. إنشاء المستخدم أولاً
        user = User.objects.create_user(
            username=self.cleaned_data['phone_primary'],
            password=self.cleaned_data['password'],
            phone_primary=self.cleaned_data['phone_primary'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
            role=User.Role.MERCHANT
        )
        
        # 2. إنشاء بروفايل التاجر
        merchant = super().save(commit=False)
        merchant.user = user
        if commit: merchant.save()
        return user
