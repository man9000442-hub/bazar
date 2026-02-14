from django import forms
from .models import User
from store.models import MerchantProfile # سنحتاج هذا لبيانات التاجر

# 1. الفورم الأساسي (للاختيار بين عميل وتاجر)
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