from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from accounts.models import User
from store.models import Product, Order, MerchantProfile

# 1. لوحة الإحصائيات السريعة للمشرف
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser]) # حماية مزدوجة: مسجل دخول + مشرف
def admin_dashboard_api(request):
    total_users = User.objects.count()
    total_orders = Order.objects.count()
    pending_merchants = MerchantProfile.objects.filter(is_approved=False).count()
    pending_products = Product.objects.filter(is_active=False).count()
    
    return Response({
        'status': 'success',
        'dashboard': {
            'total_users': total_users,
            'total_orders': total_orders,
            'pending_merchants_count': pending_merchants,
            'pending_products_count': pending_products
        }
    })

# 2. جلب التجار المعلقين (الذين ينتظرون الموافقة)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def pending_merchants_api(request):
    # تفترض أن لديك حقل is_approved في MerchantProfile
    merchants = MerchantProfile.objects.filter(is_approved=False)
    data = []
    for m in merchants:
        data.append({
            'id': m.id,
            'name': m.user.first_name,
            'phone': m.user.phone_primary,
            'national_id': m.national_id
        })
    return Response({'status': 'success', 'pending_merchants': data})

# 3. الموافقة على تاجر
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminUser])
def approve_merchant_api(request, merchant_id):
    try:
        merchant = MerchantProfile.objects.get(id=merchant_id)
        merchant.is_approved = True
        merchant.save()
        # يمكنك هنا استدعاء دالة إرسال إشعار للتاجر لتهنئته!
        return Response({'status': 'success', 'message': 'تمت الموافقة على التاجر بنجاح'})
    except MerchantProfile.DoesNotExist:
        return Response({'status': 'error', 'message': 'التاجر غير موجود'}, status=404)

# 4. جلب المنتجات المعلقة
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def pending_products_api(request):
    products = Product.objects.filter(is_active=False)
    data = []
    for p in products:
        data.append({
            'id': p.id,
            'name': p.name,
            'merchant': p.merchant.user.first_name,
            'price': str(p.base_price)
        })
    return Response({'status': 'success', 'pending_products': data})

# 5. الموافقة على منتج
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminUser])
def approve_product_api(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
        product.is_active = True
        product.save()
        return Response({'status': 'success', 'message': 'تم تفعيل المنتج وظهوره للمتجر'})
    except Product.DoesNotExist:
        return Response({'status': 'error', 'message': 'المنتج غير موجود'}, status=404)
    

from store.models import WithdrawalRequest # أضف هذا في الأعلى إذا لم يكن موجوداً

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def finance_overview_api(request):
    """API لعرض النظرة المالية وإحصائيات الأرباح للإدارة"""
    
    # حساب إجمالي المبيعات وأرباح المنصة (نتجاهل السلة والطلبات الملغية)
    valid_orders = Order.objects.exclude(status__in=['CART', 'CANCELLED', 'RETURNED'])
    
    total_platform_fees = valid_orders.aggregate(Sum('platform_fees'))['platform_fees__sum'] or 0
    total_sales = valid_orders.aggregate(Sum('final_total'))['final_total__sum'] or 0
    
    # حساب إجمالي طلبات سحب الأرباح المعلقة من التجار
    pending_withdrawals = WithdrawalRequest.objects.filter(status='PENDING').aggregate(Sum('amount'))['amount__sum'] or 0
    
    return Response({
        'status': 'success',
        'finance': {
            'total_platform_fees': str(total_platform_fees), # أرباح المنصة
            'total_sales': str(total_sales),                 # إجمالي حركة الأموال
            'pending_withdrawals': str(pending_withdrawals)  # الأموال المطلوب سحبها
        }
    })