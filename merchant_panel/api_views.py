import json
from decimal import Decimal
from datetime import timedelta
from collections import defaultdict
from django.shortcuts import render, redirect, get_object_or_404
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db import transaction
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDay, TruncMonth
from django.conf import settings

# تأكد من أن مسارات الاستدعاء تتطابق مع مشروعك
from accounts.models import User
from store.models import (
    Category, Product, ProductSize, ProductImage, Order, OrderItem, 
    Wallet, WalletTransaction, MerchantProfile, Governorate, 
    MerchantShippingRate, DepositRequest, WithdrawalRequest, 
    Offer, PaymobTransaction, SiteSetting
)
from store.paymob_utils import PaymobManager

# دالة الإشعارات
try:
    from store.utils import send_notification
except ImportError:
    def send_notification(user, title, message, link=None):
        pass

def is_merchant_valid(user):
    return user.role == 'MERCHANT' and hasattr(user, 'merchant_profile')

# ==========================================
# 1. لوحة التحكم (Dashboard)
# ==========================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def merchant_dashboard_api(request):
    user = request.user
    if not is_merchant_valid(user):
        return Response({'status': 'error', 'message': 'غير مصرح لك'}, status=403)

    merchant = user.merchant_profile
    wallet = getattr(merchant, 'wallet', None)

    balance = float(wallet.balance) if wallet else 0.00
    total_products = Product.objects.filter(merchant=merchant).count()
    
    recent_items_qs = OrderItem.objects.filter(
        product_size__product__merchant=merchant
    ).exclude(order__status__in=['CART', 'WAITING_PAYMENT']).order_by('-order__created_at')[:5]

    recent_items = [{
        'order_id': item.order.order_id,
        'product_name': item.product_size.product.name,
        'quantity': item.quantity,
        'status': item.order.get_status_display(),
        'date': item.order.created_at.strftime("%d %b"),
    } for item in recent_items_qs]

    return Response({
        'status': 'success',
        'data': { # 🔴 تم تصحيح الكلمة هنا لـ data لكي يقرأها فلاتر
            'first_name': user.first_name,
            'rank': merchant.verification_rank,
            'balance': balance,
            'total_products': total_products,
            'recent_items': recent_items
        }
    })

# ==========================================
# 2. المنتجات وإدارتها
# ==========================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def merchant_products_api(request):
    if not is_merchant_valid(request.user): return Response(status=403)
    merchant = request.user.merchant_profile
    products = Product.objects.filter(merchant=merchant).order_by('-created_at')
    
    data = []
    for p in products:
        active_offer = getattr(p, 'active_offer', None)
        has_offer = active_offer is not None and active_offer.is_currently_active
        discounted_price = active_offer.discounted_price if has_offer else p.base_price
        
        # 🔴 [الجديد] حساب الأيام المتبقية للعرض
        offer_days = 7
        if has_offer and active_offer.end_date:
            offer_days = max(1, (active_offer.end_date - timezone.now()).days)

        data.append({
            'id': p.id,
            'name': p.name,
            'category': p.category.name if p.category else '',
            'base_price': str(p.base_price),
            'has_offer': has_offer,
            'discounted_price': str(discounted_price),
            
            # 🔴 [الجديد] إرسال كل تفاصيل العرض القديم لفلاتر
            'discount_percentage': active_offer.discount_percentage if has_offer else 0,
            'free_shipping': active_offer.free_shipping if has_offer else False,
            'free_shipping_threshold': active_offer.free_shipping_threshold if has_offer else 1,
            'offer_days': offer_days,
            
            'is_active': p.is_active,
            'image': p.image.url if p.image else '',
        })
    return Response({'status': 'success', 'products': data})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def add_product_api(request):
    if not is_merchant_valid(request.user): return Response(status=403)
    merchant = request.user.merchant_profile

    current_count = Product.objects.filter(merchant=merchant).count()
    if current_count >= merchant.product_limit:
        return Response({'status': 'error', 'message': f'لقد وصلت للحد الأقصى ({merchant.product_limit} منتج)'}, status=400)

    data = request.data
    try:
        product = Product.objects.create(
            merchant=merchant,
            name=data.get('name'),
            description=data.get('description'),
            base_price=data.get('price'),
            shipping_fee=data.get('shipping_fee', 0),
            category_id=data.get('category'),
            image=request.FILES.get('main_image'),
            is_active=False
        )

        has_variations = str(data.get('has_variations')).lower() == 'true'

        if not has_variations:
            simple_stock = int(data.get('simple_stock', 0))
            if simple_stock > 0:
                ProductSize.objects.create(product=product, color_label="افتراضي", size_label="موحد", stock_quantity=simple_stock)
        else:
            variations_json = data.get('variations')
            if variations_json:
                variations = json.loads(variations_json)
                for var in variations:
                    ProductSize.objects.create(
                        product=product,
                        color_label=var.get('color'),
                        size_label=var.get('size'),
                        stock_quantity=int(var.get('qty', 0))
                    )

        send_notification(request.user, "تم إضافة المنتج بنجاح 📦", f"تم رفع المنتج '{product.name}' وهو قيد المراجعة.")
        return Response({'status': 'success', 'message': 'تم إضافة المنتج بنجاح'})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_product_api(request, product_id):
    """حذف أو إخفاء المنتج بناءً على ارتباطه بطلبات"""
    if not hasattr(request.user, 'merchant_profile'): return Response(status=403)
    
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    
    # فحص ارتباط المنتج بطلبات سابقة
    has_orders = product.variations.filter(orderitem__isnull=False).exists()
    
    if has_orders:
        product.is_active = False 
        product.save()
        return Response({'status': 'success', 'message': 'تم إخفاء المنتج بدلاً من حذفه لارتباطه بطلبات سابقة.'})
    else:
        product.delete()
        return Response({'status': 'success', 'message': 'تم حذف المنتج نهائياً.'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manage_offer_api(request, product_id):
    """إضافة، تعديل، أو إلغاء عرض على المنتج"""
    if not hasattr(request.user, 'merchant_profile'): return Response(status=403)
    
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    action = request.data.get('action') # 'add' or 'cancel'
    
    try:
        current_offer = product.active_offer
    except:
        current_offer = None

    if current_offer and current_offer.is_platform_offer and current_offer.is_active:
        return Response({'status': 'error', 'message': 'عفواً، لا يمكنك تعديل عرض تم وضعه بواسطة المنصة.'}, status=400)

    if action == 'cancel':
        if current_offer:
            current_offer.delete()
            return Response({'status': 'success', 'message': 'تم إلغاء العرض بنجاح.'})
        return Response({'status': 'error', 'message': 'لا يوجد عرض لإلغائه.'})

    elif action == 'add':
        percentage = int(request.data.get('percentage', 0))
        days = int(request.data.get('days', 7))
        free_shipping = str(request.data.get('free_shipping')).lower() == 'true'
        threshold = int(request.data.get('threshold', 1))
        
        Offer.objects.update_or_create(
            product=product,
            defaults={
                'discount_percentage': percentage,
                'start_date': timezone.now(),
                'end_date': timezone.now() + timezone.timedelta(days=days),
                'is_active': True,
                'is_platform_offer': False,
                'free_shipping': free_shipping,
                'free_shipping_threshold': threshold
            }
        )
        return Response({'status': 'success', 'message': 'تم حفظ وتفعيل العرض بنجاح 🏷️'})
        
    return Response({'status': 'error', 'message': 'إجراء غير صالح'})

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def edit_product_api(request, product_id):
    if not hasattr(request.user, 'merchant_profile'): return Response(status=403)
    merchant = request.user.merchant_profile
    product = get_object_or_404(Product, pk=product_id, merchant=merchant)
    
    if request.method == 'GET':
        variations = product.variations.all()
        is_simple = variations.count() == 1 and variations.first().color_label == 'افتراضي'
        
        vars_data = []
        if is_simple:
            simple_stock = variations.first().stock_quantity
        else:
            simple_stock = 0
            grouped = {}
            for v in variations:
                if v.color_label not in grouped: grouped[v.color_label] = []
                grouped[v.color_label].append({'size': v.size_label, 'qty': v.stock_quantity})
            for color, sizes in grouped.items():
                vars_data.append({'color': color, 'sizes': sizes})
        
        data = {
            'id': product.id, 'name': product.name, 'description': product.description,
            'price': str(product.base_price), 'category_id': str(product.category.id) if product.category else '',
            'image_url': product.image.url if product.image else '',
            'is_simple': is_simple, 'simple_stock': simple_stock, 'variations': vars_data
        }
        return Response({'status': 'success', 'product': data})

    elif request.method == 'POST':
        data = request.data
        product.name = data.get('name', product.name)
        product.description = data.get('description', product.description)
        product.base_price = data.get('price', product.base_price)
        if data.get('category'): product.category_id = data.get('category')
        
        if 'main_image' in request.FILES:
            product.image = request.FILES['main_image']
        product.save()

        has_variations = str(data.get('has_variations')).lower() == 'true'
        if not has_variations:
            var, _ = ProductSize.objects.get_or_create(product=product, color_label="افتراضي", size_label="موحد")
            var.stock_quantity = int(data.get('simple_stock', 0))
            var.save()
        else:
            variations_json = data.get('variations')
            if variations_json:
                variations_list = json.loads(variations_json)
                for var in variations_list:
                    obj, _ = ProductSize.objects.get_or_create(product=product, color_label=var.get('color'), size_label=var.get('size'))
                    obj.stock_quantity = int(var.get('qty', 0))
                    obj.save()
        
        return Response({'status': 'success', 'message': 'تم تعديل المنتج بنجاح ✏️'})

# ==========================================
# 3. الطلبات (Orders)
# ==========================================
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from store.models import Order, OrderItem

# ==========================================
# 1. دالة جلب قائمة الطلبات (محدثة لتناسب فلاتر)
# ==========================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def merchant_orders_api(request):
    if not hasattr(request.user, 'merchant_profile'): 
        return Response({'status': 'error', 'message': 'غير مصرح'}, status=403)
    
    # جلب العناصر الخاصة بهذا التاجر
    items = OrderItem.objects.filter(
        product_size__product__merchant=request.user.merchant_profile
    ).exclude(order__status__in=['CART', 'WAITING_PAYMENT']).order_by('-order__created_at')

    # تجميع الطلبات حتى لا يتكرر نفس الطلب إذا كان العميل شاري أكتر من منتج من نفس التاجر
    orders_dict = {}
    for item in items:
        o_id = item.order.order_id
        if o_id not in orders_dict:
            orders_dict[o_id] = {
                'order_id': o_id,
                'status': item.order.status,
                'status_ar': item.order.get_status_display(),
                'customer_name': item.order.recipient_name or f"{item.order.customer.first_name} {item.order.customer.last_name}",
                'address': f"{item.order.governorate.name} - {item.order.shipping_address}",
                'date': item.order.created_at.strftime("%d %b %Y, %I:%M %p")
            }

    data = list(orders_dict.values())
    return Response({'status': 'success', 'orders': data})


# ==========================================
# 2. دالة جلب تفاصيل طلب محدد (الجديدة المطابقة للصورة)
# ==========================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_merchant_order_detail(request, order_id):
    """API لجلب تفاصيل طلب معين للتاجر بدقة لتطبيق فلاتر"""
    user = request.user
    if not hasattr(user, 'merchant_profile'):
        return Response({'status': 'error', 'message': 'غير مصرح'}, status=403)
        
    merchant = user.merchant_profile
    order = get_object_or_404(Order, order_id=order_id)
    
    # جلب منتجات هذا التاجر فقط داخل الطلب
    my_items = OrderItem.objects.filter(order=order, product_size__product__merchant=merchant)
    
    if not my_items.exists():
        return Response({'status': 'error', 'message': 'الطلب غير موجود أو لا يحتوي على منتجاتك'}, status=404)

    # تجهيز قائمة المنتجات
    items_data = []
    subtotal = 0
    for item in my_items:
        items_data.append({
            'name': item.product_size.product.name,
            'size': item.product_size.size_label,
            'color': item.product_size.color_label,
            'qty': item.quantity,
            'price': str(item.price_at_purchase),
            'image': item.product_size.product.image.url if item.product_size.product.image else ''
        })
        subtotal += (item.price_at_purchase * item.quantity)

    # تجهيز بيانات الطلب الكلية
    data = {
        'order_id': order.order_id,
        'status': order.status,
        'status_ar': order.get_status_display(),
        'date': order.created_at.strftime("%d %b, %I:%M %p"),
        'customer_name': order.recipient_name or f"{order.customer.first_name} {order.customer.last_name}",
        'phone': order.shipping_phone,
        'address': f"{order.governorate.name} - {order.shipping_address}",
        'subtotal': str(subtotal),
        'shipping_cost': str(order.shipping_cost),
        'total': str(subtotal + order.shipping_cost),
        'payment_method_ar': order.get_payment_method_display(),
        'items': items_data
    }

    return Response({
        'status': 'success',
        'order': data
    })

from decimal import Decimal
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# from store.models import Order, WalletTransaction # تأكد من استدعاءاتك

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_order_status_api(request, order_id):
    if not is_merchant_valid(request.user): 
        return Response(status=403)
        
    merchant = request.user.merchant_profile
    
    try:
        order = Order.objects.get(order_id=order_id)
    except Order.DoesNotExist:
        return Response({'status': 'error', 'message': 'الطلب غير موجود'}, status=404)

    new_status = request.data.get('status')
    old_status = order.status

    # منع التكرار غير الضروري
    if new_status == old_status and new_status != 'MERCHANT_RECEIVED_RETURN':
        return Response({'status': 'info', 'message': 'الحالة لم تتغير'})

    # 🧮 حساب إجمالي عمولة المنصة
    total_commission = Decimal('0.00')
    for item in order.items.all():
        if item.product_size.product.merchant == merchant:
            pct = item.product_size.product.commission_pct / Decimal('100.0')
            total_commission += (item.price_at_purchase * pct * Decimal(item.quantity))

    wallet = merchant.wallet
    status_changed_successfully = False

    # 🔴 1. حالة استلام المرتجع (إرجاع العمولة)
    if new_status == 'MERCHANT_RECEIVED_RETURN':
        if not order.merchant_received_return:
            with transaction.atomic():
                order.merchant_received_return = True
                order.status = 'RETURNED'
                order.save()
                
                # استرداد العمولة
                wallet.balance += total_commission
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet, amount=total_commission, transaction_type='COMPENSATION',
                    related_order_id=order.order_id, 
                    description=f"استرداد عمولة المنصة (إرجاع طلب #{order.order_id})", 
                    balance_after=wallet.balance, is_released=True
                )
                print("🔥🔥🔥 جانجو وصل لسطر الإشعارات يا بطل!")
            try:
                send_notification(request.user, "تأكيد استلام المرتجع 📦", f"تم إثبات استلامك لمرتجع الطلب #{order.order_id} واسترداد العمولة.")
            except: pass
            return Response({'status': 'success', 'message': 'تم تأكيد استلام المرتجع واسترداد العمولة'})
        else:
            return Response({'status': 'error', 'message': 'تم إثبات استلام هذا المرتجع مسبقاً.'}, status=400)

    # 🔴 2. حالة بدء التحضير (هنا يتم خصم العمولة بدلاً من الشحن) 🔴
    elif new_status == 'PREPARING' and old_status == 'PENDING':
        if wallet.balance < total_commission:
            return Response({'status': 'error', 'message': f'رصيدك غير كافٍ لخصم عمولة المنصة ({total_commission} ج.م)'}, status=400)
            
        with transaction.atomic():
            order.status = 'PREPARING'
            order.save()
            
            # خصم العمولة من المحفظة
            wallet.balance -= total_commission
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet, amount=-total_commission, transaction_type='SALE',
                related_order_id=order.order_id, 
                description=f"خصم عمولة المنصة (بدء تحضير طلب #{order.order_id})", 
                balance_after=wallet.balance, is_released=True
            )
        status_changed_successfully = True

    # 🔴 3. حالة الإلغاء (استرداد العمولة لو كانت اتخصمت)
    elif new_status == 'CANCELLED':
        with transaction.atomic():
            order.status = 'CANCELLED'
            order.save()
            
            # لو كان الطلب "قيد التحضير" أو "تم الشحن" (يعني العمولة اتخصمت)، نرجعها!
            if old_status in ['PREPARING', 'SHIPPED']:
                wallet.balance += total_commission
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet, amount=total_commission, transaction_type='COMPENSATION',
                    related_order_id=order.order_id, 
                    description=f"استرداد عمولة (إلغاء طلب #{order.order_id})", 
                    balance_after=wallet.balance, is_released=True
                )
        status_changed_successfully = True

    # 🔴 4. حالة بدء الشحن والتسليم (مجرد تغيير حالة بدون خصم لأن الخصم تم في التحضير)
    else:
        order.status = new_status
        order.save()
        status_changed_successfully = True

    # 🔴 إرسال الإشعارات
    if status_changed_successfully:
        customer_notifications = {
            'PREPARING': ("جاري تحضير طلبك 📦", f"التاجر يقوم الآن بتجهيز طلبك رقم #{order.order_id}."),
            'SHIPPED': ("طلبك في الطريق إليك! 🚚", f"تم تسليم طلبك رقم #{order.order_id} لمندوب الشحن."),
            'DELIVERED': ("تم تسليم الطلب 🎉", f"تم تسليم طلبك رقم #{order.order_id} بنجاح."),
            'CANCELLED': ("إلغاء الطلب ❌", f"نأسف، تم إلغاء طلبك رقم #{order.order_id}.")
        }
        if new_status in customer_notifications:
            title, msg = customer_notifications[new_status]
            try:
                send_notification(order.customer, title, msg)
            except: pass

    return Response({'status': 'success', 'message': f'تم تغيير الحالة إلى {order.get_status_display()}'})
# ==========================================
# 4. المحفظة والسحب و Paymob
# ==========================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def merchant_wallet_api(request):
    if not is_merchant_valid(request.user): return Response(status=403)
    wallet = request.user.merchant_profile.wallet
    
    settings_obj = SiteSetting.load()
    time_threshold = timezone.now() - timedelta(hours=settings_obj.pending_balance_release_hours)
    pending_txs = WalletTransaction.objects.filter(
        wallet=wallet, transaction_type='PENDING', created_at__lte=time_threshold, is_released=False
    )
    
    if pending_txs.exists():
        with transaction.atomic():
            released_amount = sum([tx.amount for tx in pending_txs])
            for tx in pending_txs:
                tx.is_released = True
                tx.transaction_type = 'SALE'
                tx.description += " (تم التحرير)"
                tx.save()
            wallet.pending_balance -= released_amount
            wallet.balance += released_amount
            wallet.save()

    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')[:30]
    tx_data = [{
        'description': tx.description,
        'amount': str(tx.amount),
        'date': tx.created_at.strftime("%Y-%m-%d %H:%M"),
        'is_positive': tx.amount > 0
    } for tx in transactions]

    return Response({
        'status': 'success',
        'wallet': {
            'balance': str(wallet.balance),
            'pending_balance': str(wallet.pending_balance),
            'transactions': tx_data
        }
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_withdrawal_api(request):
    if not is_merchant_valid(request.user): return Response(status=403)
    wallet = request.user.merchant_profile.wallet
    settings_obj = SiteSetting.load()
    
    min_withdraw_amount = settings_obj.min_withdrawal_amount
    reserved_balance = settings_obj.min_wallet_balance
    withdrawable_balance = max(Decimal('0.00'), wallet.balance - reserved_balance)

    amount = Decimal(request.data.get('amount', 0))
    phone = request.data.get('phone')

    if amount > withdrawable_balance:
        return Response({'status': 'error', 'message': f"رصيدك غير كافٍ. يجب إبقاء {reserved_balance} ج.م في المحفظة."}, status=400)
    if amount < min_withdraw_amount:
        return Response({'status': 'error', 'message': f"أقل مبلغ يمكن سحبه هو {min_withdraw_amount} ج.م"}, status=400)

    with transaction.atomic():
        WithdrawalRequest.objects.create(merchant=request.user.merchant_profile, amount=amount, phone_number=phone)
        wallet.balance -= amount
        wallet.save()
        WalletTransaction.objects.create(
            wallet=wallet, amount=-amount, transaction_type='WITHDRAWAL',
            description="طلب سحب (قيد المراجعة)", balance_after=wallet.balance, is_released=False 
        )
    return Response({'status': 'success', 'message': 'تم تقديم طلب السحب بنجاح.'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def paymob_deposit_api(request):
    if not is_merchant_valid(request.user): return Response(status=403)
    settings_obj = SiteSetting.load()
    fee_fixed = float(settings_obj.platform_fee_fixed)
    fee_percent = float(settings_obj.platform_fee_percentage)

    net_amount = float(request.data.get('amount', 0))
    method = request.data.get('method', 'CARD')
    
    if net_amount < 10:
        return Response({'status': 'error', 'message': 'الحد الأدنى للشحن 10 ج.م'}, status=400)

    total_fees = fee_fixed + (net_amount * (fee_percent / 100.0))
    total_to_pay = net_amount + total_fees
    amount_cents = int(total_to_pay * 100)
    
    try:
        paymob = PaymobManager()
        token = paymob.get_token()
        pm_order_id = paymob.create_order(token, amount_cents)
        
        PaymobTransaction.objects.create(merchant=request.user.merchant_profile, paymob_order_id=str(pm_order_id), amount_cents=amount_cents, is_paid=False)

        user = request.user
        phone = getattr(user, 'phone_primary', '01000000000')
        billing_data = {
            "first_name": user.first_name or "Merchant", "last_name": user.last_name or "User",
            "email": user.email or "merchant@bazarna.com", "phone_number": phone,
            "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
            "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
        }

        if method == 'WALLET':
            wallet_num = request.data.get('wallet_number')
            billing_data['phone_number'] = wallet_num
            redirect_url = paymob.pay_with_wallet(token, amount_cents, pm_order_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
            return Response({'status': 'success', 'url': redirect_url})
        else:
            payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
            iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
            return Response({'status': 'success', 'url': iframe_url})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)

# ==========================================
# 5. التقارير والشحن والأقسام
# ==========================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def merchant_reports_api(request):
    if not is_merchant_valid(request.user): return Response(status=403)
    merchant = request.user.merchant_profile
    
    range_type = request.GET.get('range', 'month')
    custom_start = request.GET.get('start')
    custom_end = request.GET.get('end')
    
    today = timezone.now().date()
    start_date = today.replace(day=1)
    end_date = today

    if range_type == 'today': start_date = today
    elif range_type == 'week': start_date = today - timedelta(days=7)
    elif range_type == 'year': start_date = today.replace(month=1, day=1)
    elif range_type == 'custom' and custom_start:
        try:
            start_date = parse_date(custom_start)
            end_date = parse_date(custom_end) or today
        except: pass

    valid_order_statuses = ['PENDING', 'PREPARING', 'SHIPPED', 'DELIVERED']

    sold_items = OrderItem.objects.filter(
        product_size__product__merchant=merchant,
        order__status__in=valid_order_statuses,
        order__created_at__date__gte=start_date, order__created_at__date__lte=end_date
    )

    total_sales = sold_items.aggregate(total=Sum(F('quantity') * F('price_at_purchase')))['total'] or Decimal('0.00')
    total_orders = Order.objects.filter(merchant=merchant, status__in=valid_order_statuses, created_at__date__gte=start_date, created_at__date__lte=end_date).count()

    total_returned_orders = Order.objects.filter(merchant=merchant, status='RETURNED', created_at__date__gte=start_date, created_at__date__lte=end_date).count()
    returned_items = OrderItem.objects.filter(product_size__product__merchant=merchant, order__status='RETURNED', order__created_at__date__gte=start_date, order__created_at__date__lte=end_date)
    total_returned_value = returned_items.aggregate(total=Sum(F('quantity') * F('price_at_purchase')))['total'] or Decimal('0.00')

    top_products_qs = OrderItem.objects.filter(
        product_size__product__merchant=merchant, order__status='DELIVERED',
        order__created_at__date__gte=start_date, order__created_at__date__lte=end_date
    ).values('product_size__product__name').annotate(
        total_qty=Sum('quantity'), total_revenue=Sum(F('quantity') * F('price_at_purchase'))
    ).order_by('-total_qty')[:5]

    top_products = [{'name': p['product_size__product__name'], 'qty': p['total_qty'], 'revenue': str(p['total_revenue'])} for p in top_products_qs]

    trunc_func = TruncMonth if range_type == 'year' else TruncDay
    fmt = "%b" if range_type == 'year' else "%d %b"
    
    chart_data = sold_items.annotate(period=trunc_func('order__created_at')).values('period').annotate(total=Sum(F('quantity') * F('price_at_purchase'))).order_by('period')
    
    labels, values = [], []
    for item in chart_data:
        if item['period']:
            labels.append(item['period'].strftime(fmt))
            values.append(float(item['total']))

    if not labels:
        labels, values = ["لا توجد بيانات"], [0]

    return Response({
        'status': 'success',
        'reports': {
            'total_sales': str(total_sales),
            'total_orders': total_orders,
            'total_returned_orders': total_returned_orders,
            'total_returned_value': str(total_returned_value),
            'top_products': top_products,
            'chart': {'labels': labels, 'values': values}
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def merchant_categories_api(request):
    """جلب كل الأقسام المتاحة في النظام"""
    categories = Category.objects.all()
    data = [{'id': str(cat.id), 'name': cat.name} for cat in categories]
    return Response({'status': 'success', 'categories': data})

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def merchant_shipping_api(request):
    """جلب وتحديث أسعار الشحن"""
    if not hasattr(request.user, 'merchant_profile'): 
        return Response(status=403)
    
    merchant = request.user.merchant_profile
    governorates = Governorate.objects.all()

    if request.method == 'POST':
        rates_data = request.data.get('rates', {})
        for gov_id, price in rates_data.items():
            if not price or float(price) == 0:
                MerchantShippingRate.objects.filter(merchant=merchant, governorate_id=gov_id).delete()
            else:
                MerchantShippingRate.objects.update_or_create(
                    merchant=merchant, governorate_id=gov_id, defaults={'rate': price}
                )
        return Response({'status': 'success', 'message': 'تم حفظ أسعار الشحن بنجاح'})

    current_rates = {rate.governorate_id: rate.rate for rate in merchant.shipping_rates.all()}
    shipping_data = [{
        'id': str(gov.id),
        'name': gov.name,
        'current_rate': str(current_rates.get(gov.id, ''))
    } for gov in governorates]

    return Response({'status': 'success', 'shipping_rates': shipping_data})



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wallet_transaction_api(request):
    """API لتقديم طلبات السحب والإيداع"""
    if not hasattr(request.user, 'merchant_profile'): 
        return Response(status=403)
        
    merchant = request.user.merchant_profile
    data = request.data
    
    action = data.get('action') # 'deposit' أو 'withdrawal'
    amount = float(data.get('amount', 0))
    method = data.get('method', '')
    details = data.get('details', '')
    
    if amount <= 0:
        return Response({'status': 'error', 'message': 'المبلغ غير صحيح'}, status=400)
        
    if action == 'withdrawal' and merchant.balance < amount:
        return Response({'status': 'error', 'message': 'رصيدك الحالي لا يكفي لسحب هذا المبلغ!'}, status=400)
        
    # إنشاء المعاملة (معلقة لحين موافقة الإدارة)
    # ملاحظة: تأكد أن اسم الموديل عندك هو Transaction أو استبدله بالاسم الصحيح
    from .models import Transaction # أو حسب مسار الموديل عندك
    
    Transaction.objects.create(
        merchant=merchant,
        transaction_type=action, # 'deposit' or 'withdrawal'
        amount=amount,
        payment_method=method,
        details=details,
        status='PENDING' # معلق
    )
    
    msg = 'تم تقديم طلب السحب بنجاح وجاري مراجعته 💸' if action == 'withdrawal' else 'تم تقديم طلب الإيداع بنجاح وجاري مراجعته 💰'
    return Response({'status': 'success', 'message': msg})



from decimal import Decimal
from django.db import transaction
from store.models import WalletTransaction, WithdrawalRequest, PaymobTransaction, SiteSetting
from store.paymob_utils import PaymobManager

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_wallet_data(request):
    """جلب بيانات المحفظة ورسوم بوابات الدفع وشروط السحب"""
    if not hasattr(request.user, 'merchant_profile'): return Response(status=403)
    merchant = request.user.merchant_profile
    wallet = merchant.wallet
    settings_obj = SiteSetting.objects.first()
    
    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0.0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0.0
    min_withdraw = float(settings_obj.min_withdrawal_amount) if settings_obj else 50.0
    reserved_balance = float(settings_obj.min_wallet_balance) if settings_obj else 200.0
    
    withdrawable_balance = max(Decimal('0.00'), wallet.balance - Decimal(str(reserved_balance)))
    
    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')[:30]
    tx_data = [{
        'amount': str(abs(tx.amount)),
        'is_positive': tx.amount > 0,
        'description': tx.description,
        'date': tx.created_at.strftime("%d %b %Y, %I:%M %p")
    } for tx in transactions]
    
    return Response({
        'status': 'success',
        'wallet': {
            'balance': str(wallet.balance),
            'pending_balance': str(wallet.pending_balance),
            'transactions': tx_data,
            'fee_fixed': fee_fixed,
            'fee_percent': fee_percent,
            'min_withdraw': min_withdraw,
            'reserved_balance': reserved_balance,
            'withdrawable_balance': str(withdrawable_balance)
        }
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_wallet_withdraw(request):
    """API لطلب سحب الأرباح"""
    if not hasattr(request.user, 'merchant_profile'): return Response(status=403)
    merchant = request.user.merchant_profile
    wallet = merchant.wallet
    settings_obj = SiteSetting.objects.first()
    
    min_withdraw = Decimal(str(settings_obj.min_withdrawal_amount if settings_obj else 50.0))
    reserved_balance = Decimal(str(settings_obj.min_wallet_balance if settings_obj else 200.0))
    withdrawable_balance = max(Decimal('0.00'), wallet.balance - reserved_balance)
    
    try:
        amount = Decimal(str(request.data.get('amount', 0)))
        phone = request.data.get('phone', '')
        
        if amount > withdrawable_balance:
            return Response({'status': 'error', 'message': f'رصيدك غير كافٍ. يجب إبقاء {reserved_balance} ج.م لتغطية المرتجعات.'}, status=400)
        if amount < min_withdraw:
            return Response({'status': 'error', 'message': f'أقل مبلغ يمكن سحبه هو {min_withdraw} ج.م'}, status=400)
            
        with transaction.atomic():
            WithdrawalRequest.objects.create(merchant=merchant, amount=amount, phone_number=phone)
            wallet.balance -= amount
            wallet.save()
            WalletTransaction.objects.create(
                wallet=wallet, amount=-amount, transaction_type='WITHDRAWAL',
                description="طلب سحب (قيد المراجعة)", balance_after=wallet.balance, is_released=False
            )
            
        return Response({'status': 'success', 'message': 'تم تقديم طلب السحب بنجاح. سيتم تحويل المبلغ قريباً.'})
    except Exception as e:
        return Response({'status': 'error', 'message': 'حدث خطأ في البيانات.'}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_paymob_deposit(request):
    """API لشحن الرصيد عبر Paymob"""
    if not hasattr(request.user, 'merchant_profile'): return Response(status=403)
    merchant = request.user.merchant_profile
    settings_obj = SiteSetting.objects.first()
    
    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0.0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0.0
    
    net_amount = float(request.data.get('amount', 0))
    method = request.data.get('method', 'CARD')
    wallet_number = request.data.get('wallet_number', '')
    
    if net_amount < 10:
        return Response({'status': 'error', 'message': 'الحد الأدنى للشحن 10 ج.م'}, status=400)
        
    total_fees = fee_fixed + (net_amount * (fee_percent / 100.0))
    total_to_pay = net_amount + total_fees
    amount_cents = int(total_to_pay * 100)
    
    try:
        paymob = PaymobManager()
        token = paymob.get_token()
        pm_order_id = paymob.create_order(token, amount_cents)
        
        PaymobTransaction.objects.create(merchant=merchant, paymob_order_id=str(pm_order_id), amount_cents=amount_cents, is_paid=False)
        
        billing_data = {
            "first_name": request.user.first_name or "Merchant", "last_name": request.user.last_name or "User",
            "email": request.user.email or "merchant@domain.com", "phone_number": request.user.phone_primary,
            "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
            "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
        }
        
        if method == 'WALLET':
            if not wallet_number: return Response({'status': 'error', 'message': 'رقم المحفظة مطلوب.'}, status=400)
            billing_data['phone_number'] = wallet_number
            redirect_url = paymob.pay_with_wallet(token, amount_cents, pm_order_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
            return Response({'status': 'success', 'url': redirect_url})
        else:
            payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
            iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
            return Response({'status': 'success', 'url': iframe_url})
    except Exception as e:
        return Response({'status': 'error', 'message': 'حدث خطأ أثناء الاتصال ببوابة الدفع.'}, status=400)
    


from django.shortcuts import redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

import logging
from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from store.models import PaymobTransaction, WalletTransaction, Order, SiteSetting

logger = logging.getLogger(__name__)

# ==========================================================
# 1. دالة الـ Webhook المركزية (الجندي المجهول الذي يعمل في الخلفية)
# ==========================================================
@csrf_exempt
@api_view(['POST']) 
@permission_classes([AllowAny])
def central_paymob_callback(request):
    """Webhook مركزي يخدم التاجر (شحن محفظة) والعميل (دفع طلب) معاً"""
    try:
        data = request.data
        obj = data.get('obj', {})
        success = obj.get('success', False)
        paymob_order_id = str(obj.get('order', {}).get('id', ''))

        if not paymob_order_id:
            return HttpResponse(status=200)

        # ---------------------------------------------------------
        # السيناريو الأول: فحص هل الدفع يخص (شحن محفظة تاجر)؟
        # ---------------------------------------------------------
        merchant_tx = PaymobTransaction.objects.filter(paymob_order_id=paymob_order_id).first()
        if merchant_tx:
            if success and not merchant_tx.is_paid:
                with transaction.atomic():
                    merchant_tx.is_paid = True
                    merchant_tx.save()
                    
                    amount_paid = Decimal(str(merchant_tx.amount_cents)) / Decimal('100.0')
                    settings_obj = SiteSetting.objects.first()
                    fee_fixed = Decimal(str(settings_obj.platform_fee_fixed)) if settings_obj else Decimal('0.0')
                    fee_percent = Decimal(str(settings_obj.platform_fee_percentage)) if settings_obj else Decimal('0.0')
                    
                    # حساب المبلغ الصافي بعد خصم عمولة بيموب التقريبية
                    net_amount = (amount_paid - fee_fixed) / (Decimal('1.0') + (fee_percent / Decimal('100.0')))
                    amount_egp = round(net_amount, 2)
                    
                    wallet = merchant_tx.merchant.wallet
                    wallet.balance += amount_egp
                    wallet.save()
                    
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=amount_egp, transaction_type='DEPOSIT',
                        description=f"شحن رصيد إلكتروني - رقم العملية: {paymob_order_id}", 
                        balance_after=wallet.balance, is_released=True
                    )
            return HttpResponse(status=200)

        # ---------------------------------------------------------
        # السيناريو الثاني: فحص هل الدفع يخص (عميل يشتري أوردر)؟
        # ---------------------------------------------------------
        customer_order = Order.objects.filter(paymob_order_id=paymob_order_id).first()
        if customer_order:
            if success and customer_order.status == 'WAITING_PAYMENT':
                with transaction.atomic():
                    # تأكيد الطلب للعميل ليصبح قيد الانتظار
                    customer_order.status = 'PENDING'
                    customer_order.save()
            return HttpResponse(status=200)

        return HttpResponse(status=200)
    except Exception as e:
        logger.error(f"❌ خطأ في Webhook بيموب: {str(e)}")
        return HttpResponse(status=200)


# ==========================================================
# 2. دالة العودة للتطبيق المركزية (موظف الاستقبال)
# ==========================================================
@api_view(['GET'])
@permission_classes([AllowAny])
def central_app_return(request):
    """توجيه ذكي لتطبيقات فلاتر (التاجر أو العميل) بناءً على نوع الدفع"""
    paymob_order_id = str(request.GET.get('order', ''))
    
    # الرابط الافتراضي (تطبيق التاجر)
    app_scheme = "elbazaar://payment" 
    
    if paymob_order_id:
        # لو الطلب موجود في جدول العملاء، نغير الرابط لتطبيق العميل
        if Order.objects.filter(paymob_order_id=paymob_order_id).exists():
            app_scheme = "elbazaarcustomer://payment" # قم بتغيير هذا لاحقاً لاسم تطبيق العميل
            
    # كود إغلاق المتصفح وفتح التطبيق الصحيح
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>جاري العودة للتطبيق...</title>
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f8f9fa; }}
            .loader {{ border: 5px solid #f3f3f3; border-top: 5px solid #007bff; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 20px auto; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        </style>
    </head>
    <body>
        <h2>تمت العملية بنجاح!</h2>
        <p>جاري إعادتك للتطبيق...</p>
        <div class="loader"></div>
        <script>
            setTimeout(function() {{
                window.location.href = "{app_scheme}";
            }}, 1500);
        </script>
    </body>
    </html>
    """
    return HttpResponse(html_content)


from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django.contrib.auth import update_session_auth_hash
from store.models import TermsAndCondition

from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from django.contrib.auth import update_session_auth_hash
from store.models import TermsAndCondition, SiteSetting # 🔴 تأكد من استدعاء SiteSetting

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def merchant_profile_api(request):
    """API لجلب وتحديث بيانات التاجر"""
    user = request.user
    if not hasattr(user, 'merchant_profile'):
        return Response({'status': 'error', 'message': 'لست مسجلاً كتاجر'}, status=403)
        
    merchant = user.merchant_profile

    if request.method == 'POST':
        data = request.data
        user.first_name = data.get('first_name', user.first_name)
        user.last_name = data.get('last_name', user.last_name)
        user.email = data.get('email', user.email)
        user.phone_secondary = data.get('phone_secondary', user.phone_secondary)
        user.save()

        merchant.goods_types = data.get('goods_types', merchant.goods_types)
        merchant.goods_quantity = data.get('goods_quantity', merchant.goods_quantity)
        merchant.goods_average_price = data.get('goods_average_price', merchant.goods_average_price)
        merchant.goods_sizes = data.get('goods_sizes', merchant.goods_sizes)
        
        if 'shop_image' in request.FILES:
            merchant.shop_image = request.FILES['shop_image']
            
        merchant.save()
        return Response({'status': 'success', 'message': 'تم تحديث بياناتك بنجاح ✅'})

    # 🔴 جلب الإعدادات والسياسات
    policies = TermsAndCondition.objects.filter(is_active=True, user_type='MERCHANT')
    settings_obj = SiteSetting.objects.first()
    
    # الحد الأدنى للرصيد من الإعدادات
    min_wallet_balance = float(settings_obj.min_wallet_balance) if settings_obj else 0.0
    
    # الحد الأقصى للمنتجات (افترضت أن اسم الحقل max_products، إذا كان مختلفاً في الموديل الخاص بك، قم بتعديل الكلمة)
    max_products = getattr(merchant, 'max_products', 100) # يقرأ الحقل من التاجر، ولو مش موجود يعرض 100
    
    data = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email or '',
        'phone_primary': user.phone_primary,
        'phone_secondary': user.phone_secondary or '',
        'shop_image': merchant.shop_image.url if merchant.shop_image else '',
        
        'goods_types': merchant.goods_types or '',
        'goods_quantity': merchant.goods_quantity or '',
        'goods_average_price': merchant.goods_average_price or '',
        'goods_sizes': merchant.goods_sizes or '',
        
        'national_id': merchant.national_id or 'غير متوفر',
        'tax_register': merchant.tax_register_number or 'لا يوجد سجل ضريبي',
        
        # 🔴 البيانات الحقيقية للحدود
        'max_products_limit': max_products, 
        'min_wallet_balance': min_wallet_balance,
        
        'terms': [{'title': p.title, 'content': p.content} for p in policies.filter(document_type='TERMS')],
        'privacy': [{'title': p.title, 'content': p.content} for p in policies.filter(document_type='PRIVACY')],
        'shipping': [{'title': p.title, 'content': p.content} for p in policies.filter(document_type='SHIPPING_RETURN')],
    }
    return Response({'status': 'success', 'profile': data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_api(request):
    """API لتغيير كلمة المرور"""
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    
    if not user.check_password(old_password):
        return Response({'status': 'error', 'message': 'كلمة المرور الحالية غير صحيحة'}, status=400)
        
    if len(new_password) < 6:
        return Response({'status': 'error', 'message': 'كلمة المرور الجديدة قصيرة جداً'}, status=400)
        
    user.set_password(new_password)
    user.save()
    update_session_auth_hash(request, user) # لمنع تسجيل الخروج التلقائي
    return Response({'status': 'success', 'message': 'تم تغيير كلمة المرور بنجاح 🔒'})


from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
import logging

logger = logging.getLogger(__name__)

# 🔴 تأكد من استدعاء SiteSetting في الأعلى لو لم تكن مستدعاة
from store.models import PaymobTransaction, WalletTransaction, SiteSetting 

@csrf_exempt
@api_view(['POST']) 
@permission_classes([AllowAny])
def api_paymob_callback(request):
    """Webhook لاستقبال تأكيد الدفع من Paymob وتحديث الرصيد الصافي"""
    try:
        data = request.data
        logger.info(f"📩 Webhook Received from Paymob: {data}")
        
        obj = data.get('obj', {})
        success = obj.get('success', False)
        
        order_data = obj.get('order', {})
        paymob_order_id = order_data.get('id')

        if not paymob_order_id:
            return HttpResponse(status=200)

        pm_tx = PaymobTransaction.objects.get(paymob_order_id=str(paymob_order_id))
        
        if success and not pm_tx.is_paid:
            with transaction.atomic():
                pm_tx.is_paid = True
                pm_tx.save()
                
                # 🔴 1. جلب المبلغ الإجمالي الذي دفعه التاجر (مثلاً 208.5)
                amount_paid = Decimal(str(pm_tx.amount_cents)) / Decimal('100.0')
                
                # 🔴 2. جلب إعدادات الرسوم من قاعدة البيانات
                settings_obj = SiteSetting.objects.first()
                fee_fixed = Decimal(str(settings_obj.platform_fee_fixed)) if settings_obj else Decimal('0.0')
                fee_percent = Decimal(str(settings_obj.platform_fee_percentage)) if settings_obj else Decimal('0.0')
                
                # 🔴 3. المعادلة العكسية: استخراج المبلغ الصافي (مثلاً 200.0)
                # الصافي = (الإجمالي - الرسوم الثابتة) / (1 + (نسبة الرسوم / 100))
                net_amount = (amount_paid - fee_fixed) / (Decimal('1.0') + (fee_percent / Decimal('100.0')))
                amount_egp = round(net_amount, 2)
                
                # 4. إضافة المبلغ الصافي للمحفظة
                wallet = pm_tx.merchant.wallet
                wallet.balance += amount_egp
                wallet.save()
                
                # 5. تسجيل المعاملة في سجل التاجر بالصافي
                WalletTransaction.objects.create(
                    wallet=wallet, 
                    amount=amount_egp, 
                    transaction_type='DEPOSIT',
                    description=f"شحن رصيد (بعد خصم عمولة الدفع) - طلب #{paymob_order_id}", 
                    balance_after=wallet.balance, 
                    is_released=True
                )
                logger.info(f"✅ تم شحن محفظة التاجر بنجاح بمبلغ صافي {amount_egp}")

        return HttpResponse(status=200)

    except PaymobTransaction.DoesNotExist:
        logger.warning(f"⚠️ معاملة بيموب رقم {paymob_order_id} غير موجودة في قاعدة البيانات")
        return HttpResponse(status=200)
    except Exception as e:
        logger.error(f"❌ خطأ في الـ Webhook: {str(e)}")
        return HttpResponse(status=200)