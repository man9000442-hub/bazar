import json
import uuid
from django.contrib.auth import authenticate, login, get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken # استيراد JWT

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# تأكد من استدعاء الموديلات الخاصة بك بشكل صحيح
# from .models import User
from store.models import TermsAndCondition

User = get_user_model()

# ==========================================
# 1. تسجيل الدخول العادي
# ==========================================
# ==========================================
# 1. تسجيل الدخول العادي (برقم الهاتف)
# ==========================================
from django.contrib.auth import authenticate, login, get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

@method_decorator(csrf_exempt, name='dispatch')
class NativeLoginAPI(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get('phone') # 🔥 بنستقبل رقم التليفون
        password = request.data.get('password')

        if not phone or not password:
            return Response({
                'success': False,
                'message': 'يرجى إدخال رقم الهاتف وكلمة المرور'
            }, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        
        try:
            # 🔥 البحث عن المستخدم برقم الهاتف
            user_obj = User.objects.get(phone_primary=phone)
            # جانجو بيحتاج الـ username في المصادقة، فبنجيبه من الأوبجكت اللي لقيناه
            user = authenticate(request, username=user_obj.username, password=password)
        except User.DoesNotExist:
            user = None
        except User.MultipleObjectsReturned:
            # لو لا قدر الله فيه أكتر من يوزر بنفس الرقم
            user_obj = User.objects.filter(phone_primary=phone).first()
            user = authenticate(request, username=user_obj.username, password=password)

        if user is not None:
            if getattr(user, 'is_banned', False): 
                return Response({
                    'success': False,
                    'message': 'هذا الحساب محظور حالياً'
                }, status=status.HTTP_403_FORBIDDEN)

            # 🔥 السطر ده هو السحر اللي بيعمل Session للـ WebView
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            # في حالة إن الـ session لسه متمتش، بنجبرها تتحفظ عشان نضمن إن الـ session_key مش بـ None
            if not request.session.session_key:
                request.session.save()
                
            session_key = request.session.session_key
            refresh = RefreshToken.for_user(user)

            return Response({
                'success': True,
                'message': 'تم تسجيل الدخول بنجاح',
                'data': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh), 
                    'session_id': session_key, # 🔥 الرقم ده فلاتر هياخده للـ WebView
                    'user': {
                        'id': user.id,
                        'name': user.get_full_name() or user.username,
                        'email': user.email,
                        'role': getattr(user, 'role', 'CUSTOMER'), 
                        'phone': getattr(user, 'phone_primary', ''),
                        'referral_code': getattr(user, 'referral_code', '')
                    }
                }
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'رقم الهاتف أو كلمة المرور غير صحيحة'
        }, status=status.HTTP_401_UNAUTHORIZED)

# ==========================================
# 2. تسجيل الدخول باستخدام جوجل
# ==========================================
class NativeGoogleLoginAPI(APIView):
    """
    API لاستقبال توكن جوجل من تطبيق فلاتر،
    التحقق منه، وتسجيل دخول المستخدم (أو إنشاء حساب جديد)
    """
    permission_classes = []

    def post(self, request):
        token = request.data.get('id_token')
        requested_role = request.data.get('role', 'CUSTOMER') 

        if not token:
            return Response({'success': False, 'message': 'توكن جوجل غير موجود'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 🔥 التعديل الأول: لازم نحدد الـ Web Client ID عشان جوجل يثق في التوكن
            WEB_CLIENT_ID = "996850468337-99emd2msquh9kh5qeoavcsqfkkma03ul.apps.googleusercontent.com"
            
            # 🔥 الحل السحري لمشكلة وقت سيرفر اللينكس (بنديله سماحية 10 ثواني)
            idinfo = id_token.verify_oauth2_token(
                token, 
                google_requests.Request(), 
                WEB_CLIENT_ID,
                clock_skew_in_seconds=10 
            )            
            
            # 2. استخراج البيانات
            email = idinfo['email']
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')
            
            # 3. البحث عن المستخدم أو إنشاء حساب جديد
            user, created = User.objects.get_or_create(email=email)
            
            if created:
                # لو حساب جديد، نظبط البيانات الأساسية
                user.first_name = first_name
                user.last_name = last_name
                user.set_unusable_password() # حسابه ملوش باسورد لأنه مسجل بجوجل
                user.role = requested_role # تحديد الرتبة بناءً على اختيار التطبيق
                user.save()
            
            # التأكد إن الحساب مش محظور
            if getattr(user, 'is_banned', False) or not user.is_active:
                return Response({'success': False, 'message': 'هذا الحساب محظور'}, status=status.HTTP_403_FORBIDDEN)

            # 4. عمل Login لإنشاء Session (عشان الـ WebView)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            session_key = request.session.session_key

            # 5. 🔥 التعديل الذهبي: إنشاء JWT Token بدلاً من التوكن العادي عشان فلاتر النيتف
            refresh = RefreshToken.for_user(user)
            
            # 6. جلب حالة التاجر (لو كان تاجر)
            is_approved = True
            if getattr(user, 'role', '') == 'MERCHANT' and hasattr(user, 'merchant_profile'):
                is_approved = user.merchant_profile.is_approved

            return Response({
                'success': True,
                'message': 'تم تسجيل الدخول بجوجل بنجاح',
                'data': {
                    'access': str(refresh.access_token), # 🔥 توكن JWT
                    'refresh': str(refresh),             # 🔥 توكن التجديد
                    'session_id': session_key, 
                    'is_new_user': created, 
                    'user': {
                        'id': user.id,
                        'name': user.first_name,
                        'email': user.email,
                        'role': getattr(user, 'role', 'CUSTOMER'),
                        'is_merchant_approved': is_approved
                    }
                }
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            # 🔥 هنفضح الخطأ ونبعته للموبايل يظهر في الـ SnackBar
            return Response({'success': False, 'message': f'الخطأ من جوجل: {str(e)}'}, status=status.HTTP_401_UNAUTHORIZED)


# ==========================================
# 3. جلب بيانات البروفايل النيتف
# ==========================================
class UserProfileAPI(APIView):
    """
    API لجلب بيانات البروفايل (سواء كان عميل أو تاجر)
    """
    permission_classes = [IsAuthenticated] # لازم يكون مسجل دخول

    def get(self, request):
        user = request.user
        
        # 1. البيانات الأساسية المشتركة (للعميل والتاجر)
        data = {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone_primary': getattr(user, 'phone_primary', ''),
            'role': getattr(user, 'role', 'CUSTOMER'),
            'is_superuser': user.is_superuser,
            'is_staff': user.is_staff
        }

        # 2. لو المستخدم تاجر، هنضيف بيانات المتجر والتوثيق
        if data['role'] == 'MERCHANT' and hasattr(user, 'merchant_profile'):
            merchant = user.merchant_profile
            data['merchant_info'] = {
                'shop_image': request.build_absolute_uri(merchant.shop_image.url) if merchant.shop_image else None,
                'product_limit': merchant.product_limit,
                'minimum_balance_required': str(merchant.minimum_balance_required),
                'goods_types': merchant.goods_types or '',
                'goods_quantity': merchant.goods_quantity or '',
                'goods_average_price': merchant.goods_average_price or '',
                'goods_sizes': merchant.goods_sizes or '',
                'national_id': merchant.national_id or '',
                'tax_register_number': merchant.tax_register_number or 'غير متوفر',
            }

        return Response({
            'success': True,
            'data': data
        }, status=status.HTTP_200_OK)


# ==========================================
# 4. تحديث بيانات المتجر النيتف
# ==========================================
class UpdateMerchantProfileAPI(APIView):
    """
    API لتحديث بيانات التاجر من تطبيق فلاتر (بما فيها رفع الصورة)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser) # مهم جداً عشان نستقبل ملفات الصور من فلاتر

    def post(self, request):
        user = request.user
        
        if getattr(user, 'role', '') != 'MERCHANT' or not hasattr(user, 'merchant_profile'):
            return Response({'success': False, 'message': 'غير مصرح لك بتعديل هذه البيانات'}, status=status.HTTP_403_FORBIDDEN)
            
        merchant = user.merchant_profile

        # 1. تحديث البيانات الأساسية للمستخدم
        user.first_name = request.data.get('first_name', user.first_name)
        user.last_name = request.data.get('last_name', user.last_name)
        user.email = request.data.get('email', user.email)
        user.save()

        # 2. تحديث تفاصيل البضاعة للتاجر
        merchant.goods_types = request.data.get('goods_types', merchant.goods_types)
        merchant.goods_quantity = request.data.get('goods_quantity', merchant.goods_quantity)
        merchant.goods_average_price = request.data.get('goods_average_price', merchant.goods_average_price)
        merchant.goods_sizes = request.data.get('goods_sizes', merchant.goods_sizes)

        # 3. تحديث صورة المتجر (لو فلاتر بعت صورة جديدة)
        if 'shop_image' in request.FILES:
            merchant.shop_image = request.FILES['shop_image']

        merchant.save()

        return Response({
            'success': True,
            'message': 'تم تحديث بيانات المتجر بنجاح'
        }, status=status.HTTP_200_OK)
    

# ==========================================
# 5. جلب السياسات
# ==========================================
class PoliciesAPI(APIView):
    permission_classes = [AllowAny] # السياسات عامة مش محتاجة توكن

    def get(self, request):
        # لو مبعتش نوع، هيعتبره عميل كافتراضي
        user_type = request.GET.get('user_type', 'CUSTOMER') 
        
        # بنجيب السياسات المفعلة الخاصة بالنوع ده ومترتبة
        policies = TermsAndCondition.objects.filter(is_active=True, user_type=user_type).order_by('order')
        
        # بنجهز قاموس (Dict) عشان فلاتر يقراه بسهولة
        data = {
            'TERMS': [],
            'PRIVACY': [],
            'SHIPPING_RETURN': []
        }
        
        for p in policies:
            if p.document_type in data:
                data[p.document_type].append({
                    'title': p.title,
                    'content': p.content,
                    'order': p.order
                })
                
        return Response({'success': True, 'data': data})


# ==========================================
# 6. تغيير كلمة المرور
# ==========================================
class ChangePasswordAPI(APIView):
    permission_classes = [IsAuthenticated] # لازم يكون مسجل دخول بالتوكن

    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        # 1. التأكد من إدخال البيانات
        if not old_password or not new_password:
            return Response({'success': False, 'message': 'يرجى إدخال جميع الحقول'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. التأكد من صحة الباسورد القديم
        if not user.check_password(old_password):
            return Response({'success': False, 'message': 'كلمة المرور الحالية غير صحيحة'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. حفظ الباسورد الجديد
        user.set_password(new_password)
        user.save()

        return Response({'success': True, 'message': 'تم تغيير كلمة المرور بنجاح!'}, status=status.HTTP_200_OK)
    

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth import login
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model

User = get_user_model()

# 1. API تسجيل العميل
class NativeCustomerSignupAPI(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get('phone_primary')
        password = request.data.get('password')
        username = request.data.get('username')

        if User.objects.filter(phone_primary=phone).exists():
            return Response({'success': False, 'message': 'رقم الهاتف مسجل بالفعل'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=username).exists():
            return Response({'success': False, 'message': 'اسم المستخدم مستخدم بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

        # إنشاء المستخدم
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=request.data.get('first_name', ''),
            last_name=request.data.get('last_name', ''),
            phone_primary=phone,
            role='CUSTOMER'
        )

        # تسجيل الدخول وتوليد التوكن
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        refresh = RefreshToken.for_user(user)

        return Response({
            'success': True,
            'message': 'تم إنشاء الحساب بنجاح',
            'data': {
                'access': str(refresh.access_token),
                'session_id': request.session.session_key,
                'user': {'id': user.id, 'name': user.first_name, 'role': 'CUSTOMER'}
            }
        }, status=status.HTTP_201_CREATED)

# 2. API تسجيل التاجر (مع استقبال الصور)
class NativeMerchantSignupAPI(APIView):
    permission_classes = [AllowAny]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        phone = request.data.get('phone_primary')
        password = request.data.get('password')

        if User.objects.filter(phone_primary=phone).exists():
            return Response({'success': False, 'message': 'رقم الهاتف مسجل بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

        # إنشاء المستخدم
        user = User.objects.create_user(
            username=phone, # نستخدم الهاتف كـ username للتاجر
            password=password,
            first_name=request.data.get('first_name', ''),
            last_name=request.data.get('last_name', ''),
            phone_primary=phone,
            role='MERCHANT'
        )

        # حفظ بيانات التاجر الإضافية (بافتراض وجود Profile أو حفظها في اليوزر)
        if hasattr(user, 'merchant_profile'):
            merchant = user.merchant_profile
            merchant.goods_types = request.data.get('goods_types', '')
            merchant.goods_quantity = request.data.get('goods_quantity', '')
            merchant.goods_average_price = request.data.get('goods_average_price', '')
            merchant.national_id = request.data.get('national_id', '')
            
            # حفظ الصور
            if 'id_card_front' in request.FILES: merchant.id_card_front = request.FILES['id_card_front']
            if 'id_card_back' in request.FILES: merchant.id_card_back = request.FILES['id_card_back']
            if 'shop_image' in request.FILES: merchant.shop_image = request.FILES['shop_image']
            
            merchant.save()

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        refresh = RefreshToken.for_user(user)

        return Response({
            'success': True,
            'message': 'تم إرسال طلب انضمامك كتاجر بنجاح',
            'data': {
                'access': str(refresh.access_token),
                'session_id': request.session.session_key,
                'user': {'id': user.id, 'name': user.first_name, 'role': 'MERCHANT'}
            }
        }, status=status.HTTP_201_CREATED)
    

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import UserFCMToken

# في ملف views.py الخاص بحسابات المستخدمين
from rest_framework.decorators import api_view, permission_classes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.models import UserFCMToken # تأكد إن مسار الموديل صح

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_fcm_token(request):
    fcm_token = request.data.get('fcm_token')
    
    if not fcm_token:
        return Response({'success': False, 'message': 'التوكين مطلوب'}, status=400)
    
    # البحث عن التوكين، لو موجود نحدث المالك بتاعه، لو مش موجود ننشئه
    token_obj = UserFCMToken.objects.filter(token=fcm_token).first()
    if token_obj:
        if token_obj.user != request.user:
            token_obj.user = request.user
            token_obj.save()
    else:
        UserFCMToken.objects.create(user=request.user, token=fcm_token)
    
    return Response({'success': True, 'message': 'تم حفظ توكين الإشعارات بنجاح'}, status=200)