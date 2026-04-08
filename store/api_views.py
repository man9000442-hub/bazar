
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from accounts.models import User
from store.models import (
    Product, Category, Order, OrderItem, ProductSize, 
    Governorate, SiteSetting, Favorite, Offer, 
    Banner, DeliveryComplaint, ProductReview, PersonalVoucher
)

logger = logging.getLogger(__name__)

# ==========================================
# 1. الرئيسية والمنتجات
# ==========================================

@api_view(['GET'])
@permission_classes([AllowAny])
def home_api(request):
    """جلب بيانات الصفحة الرئيسية للعميل"""
    category_id = request.GET.get('category')
    search_query = request.GET.get('q', '')

    banners = Banner.objects.all()
    categories = Category.objects.all()
    
    # المنتجات والعروض النشطة
    products_query = Product.objects.filter(merchant__is_approved=True)
    if category_id:
        products_query = products_query.filter(category_id=category_id)
    if search_query:
        products_query = products_query.filter(name__icontains=search_query)

    offers = Product.objects.filter(active_offer__isnull=False, merchant__is_approved=True)

    # تجهيز البيانات كـ JSON
    data = {
        'banners': [{'id': b.id, 'image': b.image.url if b.image else '', 'link': b.link} for b in banners],
        'categories': [{'id': c.id, 'name': c.name, 'image': c.image.url if c.image else ''} for c in categories],
        'recent_products': [],
        'special_offers': [],
        'unread_notifications_count': request.user.notifications.filter(is_read=False).count() if request.user.is_authenticated else 0
    }

    # تنسيق المنتجات
    for p in products_query.order_by('-id')[:20]:
        prod_data = {
            'id': p.id,
            'name': p.name,
            'category': p.category.name,
            'base_price': str(p.base_price),
            'image': p.image.url if p.image else '',
            'has_offer': False,
        }
        if hasattr(p, 'active_offer') and p.active_offer and p.active_offer.is_currently_active():
            prod_data['has_offer'] = True
            prod_data['discount_percentage'] = p.active_offer.discount_percentage
            prod_data['discounted_price'] = str(p.active_offer.discounted_price)
        data['recent_products'].append(prod_data)

    return Response({'status': 'success', 'data': data})


@api_view(['GET'])
@permission_classes([AllowAny])
def product_detail_api(request, product_id):
    """جلب تفاصيل المنتج (الألوان والمقاسات والتقييمات)"""
    product = get_object_or_404(Product, id=product_id)
    
    is_fav = False
    if request.user.is_authenticated:
        is_fav = Favorite.objects.filter(user=request.user, product=product).exists()

    # تجهيز الألوان والمقاسات (بناءً على المنطق الخاص بك في الـ Template)
    variations = []
    colors = set()
    for variant in product.variations.all():
        if variant.stock_quantity > 0:
            colors.add(variant.color_label)
            variations.append({
                'id': variant.id,
                'color': variant.color_label,
                'size': variant.size_label,
                'stock': variant.stock_quantity
            })

    data = {
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'base_price': str(product.base_price),
        'image': product.image.url if product.image else '',
        'images': [img.image.url for img in product.images.all()],
        'merchant': {
            'id': product.merchant.id,
            'name': f"{product.merchant.user.first_name} {product.merchant.user.last_name}",
            'shop_image': product.merchant.shop_image.url if product.merchant.shop_image else '',
            'rank': getattr(product.merchant, 'verification_rank', 'NONE'),
        },
        'average_rating': getattr(product, 'average_rating', 0),
        'reviews_count': getattr(product, 'reviews_count', 0),
        'available_colors': list(colors),
        'variations': variations,
        'is_favorite': is_fav,
    }

    # العروض
    if hasattr(product, 'active_offer') and product.active_offer and product.active_offer.is_currently_active():
        data['offer'] = {
            'discount_percentage': product.active_offer.discount_percentage,
            'discounted_price': str(product.active_offer.discounted_price),
            'end_date': product.active_offer.end_date.isoformat(),
            'free_shipping': product.active_offer.free_shipping,
            'free_shipping_threshold': product.active_offer.free_shipping_threshold
        }

    return Response({'status': 'success', 'data': data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_favorite_api(request, product_id):
    """إضافة/إزالة من المفضلة"""
    product = get_object_or_404(Product, id=product_id)
    fav, created = Favorite.objects.get_or_create(user=request.user, product=product)
    
    if not created:
        fav.delete()
        return Response({'status': 'success', 'added': False, 'message': 'تم الإزالة من المفضلة'})
    return Response({'status': 'success', 'added': True, 'message': 'تم الإضافة للمفضلة'})


# ==========================================
# 2. السلة والطلب (Cart & Checkout)
# ==========================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cart_data_api(request):
    """جلب محتويات السلة وتجهيز شاشة الدفع (تطابق checkout.html)"""
    # نفترض أن السلة هي طلب بحالة CART في الداتابيز
    order = Order.objects.filter(customer=request.user, status='CART').first()
    
    if not order or not order.items.exists():
        return Response({'status': 'success', 'is_empty': True})

    items_data = []
    cart_total = Decimal('0.00')
    
    for item in order.items.all():
        cart_total += item.total_price
        items_data.append({
            'item_id': item.id,
            'product_name': item.product_size.product.name,
            'image': item.product_size.product.image.url if item.product_size.product.image else '',
            'size': item.product_size.size_label,
            'color': item.product_size.color_label,
            'quantity': item.quantity,
            'price': str(item.price_at_purchase),
            'total_price': str(item.total_price),
            'merchant_id': item.product_size.product.merchant.id,
            'merchant_name': item.product_size.product.merchant.user.first_name,
        })

    # المحافظات
    governorates = [{'id': g.id, 'name': g.name} for g in Governorate.objects.all()]
    
    # القسائم الشخصية
    vouchers = PersonalVoucher.objects.filter(customer=request.user, remaining_items__gt=0)
    vouchers_data = [{
        'code': v.code,
        'title': v.title,
        'discount_percentage': v.discount_percentage,
        'max_discount_amount': str(v.max_discount_amount),
        'free_shipping': v.free_shipping
    } for v in vouchers]

    # رسوم المنصة
    settings_obj = SiteSetting.objects.first()
    
    data = {
        'is_empty': False,
        'order_id': order.id,
        'items': items_data,
        'cart_total': str(cart_total),
        'governorates': governorates,
        'personal_vouchers': vouchers_data,
        'referral_balance': str(request.user.referral_balance),
        'platform_fee_fixed': str(settings_obj.platform_fee_fixed) if settings_obj else "0",
        'platform_fee_percent': str(settings_obj.platform_fee_percentage) if settings_obj else "0",
    }
    return Response({'status': 'success', 'data': data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_order_api(request):
    """إنشاء الطلب النهائي وتحديد الحالة بناءً على طريقة الدفع"""
    order = Order.objects.filter(customer=request.user, status='CART').first()
    if not order or not order.items.exists():
        return Response({'status': 'error', 'message': 'السلة فارغة'}, status=400)

    data = request.data
    gov_id = data.get('city_id')
    address = data.get('address')
    recipient_name = data.get('recipient_name')
    phone = data.get('phone')
    payment_method = data.get('payment_method', 'COD') # COD, ONLINE, WALLET
    wallet_number = data.get('wallet_number', '')
    use_referral = data.get('use_wallet', False)
    
    if not all([gov_id, address, recipient_name, phone]):
        return Response({'status': 'error', 'message': 'الرجاء إكمال بيانات الشحن'}, status=400)

    try:
        with transaction.atomic():
            # 1. تحديث بيانات الطلب
            order.governorate_id = gov_id
            order.shipping_address = address
            order.recipient_name = recipient_name
            order.shipping_phone = phone
            order.payment_method = payment_method
            
            # (هنا يمكنك استدعاء دالة calc_shipping_logic لحساب الشحن بدقة بناءً على المحافظة والتجار)
            # order.shipping_cost = ... 
            
            # 2. تطبيق الخصومات
            if use_referral and request.user.referral_balance > 0:
                # تطبيق خصم الإحالة
                pass 
                
            # 3. رسوم المنصة (لو الدفع إلكتروني)
            if payment_method in ['ONLINE', 'WALLET']:
                settings_obj = SiteSetting.objects.first()
                # حساب الرسوم
                order.status = 'WAITING_PAYMENT' # في انتظار الدفع عبر بيموب
            else:
                order.status = 'PENDING' # كاش، يذهب للتاجر مباشرة
            
            order.created_at = timezone.now()
            order.save()

        # إرجاع الاستجابة (إذا كان الدفع إلكترونياً يجب توجيه التطبيق لشاشة الدفع)
        return Response({
            'status': 'success', 
            'message': 'تم إنشاء الطلب بنجاح', 
            'order_id': order.id,
            'payment_method': payment_method,
            'requires_payment': payment_method != 'COD'
        })
    except Exception as e:
        logger.error(f"خطأ في إنشاء الطلب: {e}")
        return Response({'status': 'error', 'message': 'حدث خطأ أثناء معالجة الطلب'}, status=500)


# ==========================================
# 3. الطلبات، تأكيد الاستلام، والشكاوى
# ==========================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_orders_api(request):
    """جلب طلبات العميل السابقة"""
    orders = Order.objects.filter(customer=request.user).exclude(status='CART').order_by('-created_at')
    data = []
    for o in orders:
        data.append({
            'id': o.id,
            'order_id': o.order_id if hasattr(o, 'order_id') else o.id,
            'status': o.status,
            'status_display': o.get_status_display(),
            'created_at': o.created_at.strftime("%Y-%m-%d %H:%M"),
            'final_total': str(getattr(o, 'final_total', 0)),
            'payment_method': o.get_payment_method_display() if hasattr(o, 'get_payment_method_display') else o.payment_method,
            'items_images': [item.product_size.product.image.url for item in o.items.all() if item.product_size.product.image][:4]
        })
    return Response({'status': 'success', 'data': data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_delivery_action_api(request, order_id):
    """
    المنطق العبقري لشاشة (confirm_delivery.html):
    - action = 'confirm': تأكيد الاستلام وإرسال تقييم.
    - action = 'reject': فتح شكوى وتجميد أرباح التاجر.
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    action = request.data.get('action') # 'confirm' or 'reject'

    if order.status not in ['DELIVERED', 'RETURNED']:
        return Response({'status': 'error', 'message': 'حالة الطلب لا تسمح بهذا الإجراء'}, status=400)

    try:
        with transaction.atomic():
            if action == 'confirm':
                if order.status == 'DELIVERED':
                    # حفظ التقييمات
                    rating = request.data.get('rating')
                    comment = request.data.get('review_comment', '')
                    if rating:
                        # نفترض أن التقييم يضاف لأول منتج في الطلب كعينة (أو لكل المنتجات حسب تصميمك)
                        for item in order.items.all():
                            ProductReview.objects.update_or_create(
                                user=request.user, product=item.product_size.product,
                                defaults={'rating': int(rating), 'comment': comment}
                            )
                    order.status = 'COMPLETED' # إنهاء الطلب بنجاح وإضافة رصيد التاجر
                    order.save()
                    return Response({'status': 'success', 'message': 'شكراً لتقييمك! تم تأكيد الاستلام.'})

                elif order.status == 'RETURNED':
                    # تأكيد المرتجع
                    order.status = 'RETURN_COMPLETED'
                    order.save()
                    return Response({'status': 'success', 'message': 'تم تأكيد المرتجع بنجاح.'})

            elif action == 'reject':
                reason = request.data.get('reason', '')
                whatsapp = request.data.get('whatsapp_number', '')
                
                if not whatsapp:
                    return Response({'status': 'error', 'message': 'رقم الواتساب مطلوب للتحقيق'}, status=400)

                # 🔴 إنشاء شكوى وتجميد الطلب (نفس المنطق في التمبلت)
                DeliveryComplaint.objects.create(
                    order=order,
                    customer=request.user,
                    complaint_text=f"رقم التواصل: {whatsapp}\nالسبب: {reason}",
                    is_resolved=False
                )
                
                # تغيير حالة الطلب لتنبيه الإدارة
                order.status = 'COMPLAINT_OPENED'
                order.save()
                
                return Response({
                    'status': 'success', 
                    'message': 'تم إرسال الشكوى العاجلة للإدارة بنجاح. سيتم التواصل معك قريباً.'
                })

    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


# ==========================================
# 4. مركز الدعوات (Referral Center)
# ==========================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def referral_center_api(request):
    """شاشة مركز الدعوات (رصيد الإحالة)"""
    user = request.user
    
    if request.method == 'GET':
        return Response({
            'status': 'success',
            'data': {
                'referral_code': user.referral_code,
                'referral_balance': str(user.referral_balance),
                # يمكن إضافة شروط هل يستحق إدخال كود أم لا بناءً على تاريخ التسجيل
                'is_eligible_to_enter_code': not user.invited_by 
            }
        })
        
    elif request.method == 'POST':
        code = request.data.get('code')
        if not code:
            return Response({'status': 'error', 'message': 'يرجى إدخال الكود'}, status=400)
            
        if user.invited_by:
            return Response({'status': 'error', 'message': 'لقد قمت باستخدام كود دعوة مسبقاً'}, status=400)
            
        if code.upper() == user.referral_code:
            return Response({'status': 'error', 'message': 'لا يمكنك استخدام الكود الخاص بك!'}, status=400)
            
        try:
            friend = User.objects.get(referral_code=code.upper())
            with transaction.atomic():
                user.invited_by = friend
                # إضافة الرصيد للمستخدم وصديقه (حسب إعداداتك)
                settings_obj = SiteSetting.objects.first()
                bonus = getattr(settings_obj, 'referral_bonus_amount', Decimal('10.0'))
                
                user.referral_balance += bonus
                user.save()
                
                friend.referral_balance += bonus
                friend.save()
                
            return Response({'status': 'success', 'message': f'مبروك! تم تفعيل الكود وحصلت على {bonus} ج.م'})
        except User.DoesNotExist:
            return Response({'status': 'error', 'message': 'الكود غير صحيح'}, status=404)




import requests
from django.conf import settings
# تأكد من استدعاءاتك فوق...

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def place_order_api(request):
    """تأكيد الطلب النهائي وتوليد رابط بيموب للعميل"""
    order = Order.objects.filter(customer=request.user, status='CART').first()
    
    if not order or not order.items.exists():
        return Response({'status': 'error', 'message': 'السلة فارغة'}, status=400)

    data = request.data
    gov_id = data.get('city_id')
    address = data.get('address')
    recipient_name = data.get('recipient_name')
    phone = data.get('phone')
    payment_method = data.get('payment_method', 'COD') # COD, ONLINE, WALLET
    wallet_number = data.get('wallet_number', '')
    use_referral = data.get('use_wallet', False)
    
    if not all([gov_id, address, recipient_name, phone]):
        return Response({'status': 'error', 'message': 'الرجاء إكمال بيانات الشحن'}, status=400)

    try:
        with transaction.atomic():
            # 1. تحديث بيانات الشحن الأساسية للطلب
            order.governorate_id = gov_id
            order.shipping_address = address
            order.recipient_name = recipient_name
            order.shipping_phone = phone
            order.payment_method = payment_method
            
            # 🔴 قم هنا بحساب تكلفة الشحن والخصومات والإجمالي النهائي (final_total)
            # order.shipping_cost = ...
            # order.final_total = ...
            
            total_to_pay = order.final_total # هذا هو الرقم النهائي الذي سيدفعه العميل

            # 2. تحديد الحالة ومسار الدفع
            if payment_method == 'COD':
                # الدفع كاش: الطلب يكتمل فوراً ويذهب للتاجر
                order.status = 'PENDING'
                order.created_at = timezone.now()
                order.save()
                
                return Response({
                    'status': 'success', 
                    'message': 'تم إنشاء الطلب بنجاح (الدفع عند الاستلام)', 
                    'order_id': order.id,
                    'requires_payment': False
                })

            else:
                # الدفع الإلكتروني (فيزا أو محفظة): نكلم بيموب أولاً
                order.status = 'WAITING_PAYMENT'
                order.created_at = timezone.now()
                order.save() # نحفظ مؤقتاً لنحصل على رقم الطلب

                # ==========================================
                # 🚀 اتصال بيموب (Paymob Integration) 🚀
                # ==========================================
                amount_cents = int(total_to_pay * 100)
                
                # 🔴 ضع بياناتك هنا 🔴
                API_KEY = "ضع_الـ_API_KEY_الخاص_ببيموب_هنا"
                CARD_INTEGRATION_ID = 1234567   # للفيزا
                WALLET_INTEGRATION_ID = 7654321 # للمحفظة
                CARD_IFRAME_ID = 123456         # إطار الفيزا

                # خطوة 1: Auth
                auth_resp = requests.post("https://accept.paymob.com/api/auth/tokens", json={"api_key": API_KEY})
                auth_token = auth_resp.json().get('token')

                # خطوة 2: Order Creation
                order_data = {
                    "auth_token": auth_token,
                    "delivery_needed": "false",
                    "amount_cents": amount_cents,
                    "currency": "EGP",
                    "items": [],
                    "merchant_order_id": f"CUST_ORD_{order.id}_{timezone.now().timestamp()}" # رقم فريد لمنع التكرار
                }
                order_resp = requests.post("https://accept.paymob.com/api/ecommerce/orders", json=order_data)
                paymob_order_id = str(order_resp.json().get('id'))

                # 🔴 الأهم: حفظ رقم طلب بيموب في طلب العميل لكي يجده الكول باك لاحقاً
                order.paymob_order_id = paymob_order_id
                order.save()

                # خطوة 3: Payment Key
                integration_id = WALLET_INTEGRATION_ID if payment_method == 'WALLET' else CARD_INTEGRATION_ID
                
                billing_data = {
                    "apartment": "NA", "email": request.user.email or "customer@test.com", "floor": "NA",
                    "first_name": request.user.first_name or "Customer", "street": "NA", "building": "NA",
                    "phone_number": wallet_number if payment_method == 'WALLET' else "+201000000000",
                    "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG",
                    "last_name": request.user.last_name or "User", "state": "NA"
                }

                key_data = {
                    "auth_token": auth_token, "amount_cents": amount_cents, "expiration": 3600,
                    "order_id": paymob_order_id, "billing_data": billing_data,
                    "currency": "EGP", "integration_id": integration_id
                }
                key_resp = requests.post("https://accept.paymob.com/api/acceptance/payment_keys", json=key_data)
                payment_token = key_resp.json().get('token')

                # خطوة 4: توليد الرابط النهائي
                if payment_method == 'WALLET':
                    pay_data = {
                        "source": {"identifier": wallet_number, "subtype": "WALLET"},
                        "payment_token": payment_token
                    }
                    pay_resp = requests.post("https://accept.paymob.com/api/acceptance/payments/pay", json=pay_data)
                    payment_url = pay_resp.json().get('redirect_url')
                else:
                    payment_url = f"https://accept.paymob.com/api/acceptance/iframes/{CARD_IFRAME_ID}?payment_token={payment_token}"

                return Response({
                    'status': 'success',
                    'message': 'جاري توجيهك للدفع...',
                    'order_id': order.id,
                    'requires_payment': True,
                    'payment_url': payment_url # فلاتر سيقوم بفتح هذا الرابط
                })

    except Exception as e:
        logger.error(f"خطأ في إنشاء الطلب والدفع: {e}")
        return Response({'status': 'error', 'message': 'حدث خطأ أثناء معالجة الطلب وبوابة الدفع'}, status=500)
    
from django.http import JsonResponse
# 🔥 استدعي الموديل بتاعك هنا (تأكد من اسم التطبيق اللي جواه الموديل، مثلاً store أو core أو pages)
from .models import TermsAndCondition 

def api_customer_terms(request):
    try:
        # 1. بنسحب كل الشروط المفعلة الخاصة بالعملاء ومترتبة حسب حقل (order)
        customer_terms = TermsAndCondition.objects.filter(
            is_active=True, 
            user_type='CUSTOMER'
        ).order_by('order')

        # 2. لو مفيش شروط في الداتا بيز
        if not customer_terms.exists():
            return JsonResponse({'content': 'لم يتم إضافة الشروط والأحكام بعد.'}, status=200, json_dumps_params={'ensure_ascii': False})

        # 3. تجميع البنود في نص واحد منسق
        terms_text = "الشروط والأحكام وسياسة الخصوصية:\n\n"
        
        for item in customer_terms:
            # بنحط عنوان البند (title) وتحته النص (content) وبينهم مسافات عشان يبقى شكلهم حلو في فلاتر
            terms_text += f"📌 {item.title}\n{item.content}\n\n"
        
        # 4. إرسال النص النهائي لفلاتر
        return JsonResponse({'content': terms_text.strip()}, status=200, json_dumps_params={'ensure_ascii': False})
    
    except Exception as e:
        return JsonResponse({'content': 'حدث خطأ في السيرفر أثناء جلب الشروط.'}, status=500, json_dumps_params={'ensure_ascii': False})



