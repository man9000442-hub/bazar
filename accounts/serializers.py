from rest_framework import serializers
from .models import User
try:
    from store.models import MerchantProfile
except ImportError:
    pass

class UserSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, required=False)
    referral_balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_merchant_approved = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'phone_primary', 'role', 'balance', 'referral_balance', 'referral_code', 'is_merchant_approved']

    def get_is_merchant_approved(self, obj):
        try:
            return obj.merchant_profile.is_approved
        except Exception:
            return False

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Ensure fallback for balance if not directly a field on User model
        if 'balance' not in data or data['balance'] is None:
            data['balance'] = getattr(instance, 'balance', '0.00')
        return data

class MerchantProfileSerializer(serializers.ModelSerializer):
    class Meta:
        if 'MerchantProfile' in globals():
            model = MerchantProfile
        else:
            model = None
            
        fields = [
            'national_id', 'id_card_front', 'id_card_back', 
            'shop_image', 'tax_register', 'goods_quantity', 
            'goods_types', 'goods_average_price', 'goods_sizes'
        ]

from django.contrib.auth.password_validation import validate_password

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_primary', 'password', 'password_confirm', 'role']
        
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "كلمتا المرور غير متطابقتين."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm') # نحذفها لأننا لا نخزنها
        # نستخدم create_user لكي يتم تشفير كلمة المرور (Hashing)
        user = User.objects.create_user(
            username=validated_data['phone_primary'], # نستخدم رقم الهاتف كـ username مؤقتاً أو يمكنك تغييره
            phone_primary=validated_data['phone_primary'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', 'CUSTOMER')
        )
        return user