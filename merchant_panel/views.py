# ==========================================
# 1. الاستدعاءات (Imports) مرتبة ومنظمة
# ==========================================
import json
from decimal import Decimal
from datetime import timedelta
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.db import transaction
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDay, TruncMonth
from django.conf import settings
from django.http import HttpResponse

# موديلات النظام
from accounts.models import User
from store.models import (
    Category, Product, ProductSize, ProductImage, Order, OrderItem, 
    Wallet, WalletTransaction, MerchantProfile, Governorate, 
    MerchantShippingRate, DepositRequest, WithdrawalRequest, 
    Offer, PaymobTransaction, SiteSetting
)
from store.paymob_utils import PaymobManager

# ==========================================
# إعداد دوال الإشعارات (الداخلية والموبايل)
# ==========================================
try:
    from store.utils import send_notification
except ImportError:
    def send_notification(user, title, message, link=None):
        pass

# 🔥 استدعاء دالة إشعارات الموبايل (Push Notifications) الجديدة
try:
    from store.utils import send_push_to_user 
except ImportError:
    def send_push_to_user(user, title, body):
        pass


@login_required
def merchant_pending_approval(request):
    # لو التاجر أصلاً متفعل، رجعه للداشبورد عشان ميقفش هنا بالغلط
    if hasattr(request.user, 'merchant_profile') and request.user.merchant_profile.is_approved:
        return redirect('merchant_dashboard')
    
    return render(request, 'merchant/pending_approval.html')

# ==========================================
# 2. الدوال المساعدة (Helper Functions)
# ==========================================
def is_merchant(user):
    """التحقق مما إذا كان المستخدم تاجراً معتمداً"""
    return user.role == User.Role.MERCHANT and hasattr(user, 'merchant_profile') and user.merchant_profile.is_approved


# ==========================================
# 3. دوال لوحة تحكم التاجر (Merchant Views)
# ==========================================

@login_required
def dashboard(request):
    """الرئيسية والإحصائيات السريعة للتاجر"""
    if not is_merchant(request.user):
        return redirect('home')

    merchant = request.user.merchant_profile
    total_products = Product.objects.filter(merchant=merchant).count()
    
    try:
        balance = merchant.wallet.balance
    except:
        balance = 0

    recent_items = OrderItem.objects.filter(
        product_size__product__merchant=merchant
    ).exclude(
        order__status__in=['CART', 'WAITING_PAYMENT']
    ).order_by('-order__created_at')

    return render(request, 'merchant/dashboard.html', {
        'total_products': total_products,
        'balance': balance,
        'recent_items': recent_items
    })


@login_required
def my_products(request):
    """عرض قائمة منتجات التاجر"""
    if not is_merchant(request.user):
        return redirect('home')
        
    products = Product.objects.filter(merchant=request.user.merchant_profile).order_by('-created_at')
    return render(request, 'merchant/products.html', {'products': products})


@login_required
def add_product(request):
    """إضافة منتج جديد بمتغيرات أو بدون"""
    if not is_merchant(request.user): 
        return redirect('home')

    merchant = request.user.merchant_profile
    
    # فحص الحد الأقصى للمنتجات
    current_count = Product.objects.filter(merchant=merchant).count()
    if current_count >= merchant.product_limit:
        messages.error(request, f"لقد وصلت للحد الأقصى المسموح لك ({merchant.product_limit} منتج). يرجى التواصل مع الإدارة لزيادة الحد.")
        return redirect('merchant_products')

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        shipping_fee = request.POST.get('shipping_fee', 0)
        category_id = request.POST.get('category')
        main_image = request.FILES.get('main_image')

        product = Product.objects.create(
            merchant=merchant,
            name=name, description=description, base_price=price,
            shipping_fee=shipping_fee, category_id=category_id,
            image=main_image, is_active=False
        )

        has_variations = request.POST.get('has_variations') == 'on'
        
        if not has_variations:
            simple_stock = int(request.POST.get('simple_stock', 0))
            if simple_stock > 0:
                ProductSize.objects.create(
                    product=product, color_label="افتراضي", size_label="موحد", stock_quantity=simple_stock
                )
        else:
            for key in request.POST:
                if key.startswith('color_group_'):
                    group_id = key.split('_')[-1]
                    color_name = request.POST.get(key)
                    sizes = request.POST.getlist(f'sizes_group_{group_id}[]')
                    qtys = request.POST.getlist(f'qtys_group_{group_id}[]')
                    
                    for i in range(len(sizes)):
                        if sizes[i] and qtys[i]:
                            ProductSize.objects.create(
                                product=product, color_label=color_name, size_label=sizes[i], stock_quantity=qtys[i]
                            )

        for img in request.FILES.getlist('gallery_images'):
            ProductImage.objects.create(product=product, image=img)

        # --- [إشعار الداخلي] ---
        send_notification(
            user=request.user,
            title="تم إضافة المنتج بنجاح 📦",
            message=f"تم رفع المنتج '{product.name}' إلى متجرك بنجاح وهو الآن قيد المراجعة.",
            link="/merchant/products/"
        )

        # 🔥 --- [إشعار الموبايل Push Notification] ---
        send_push_to_user(
            user=request.user,
            title="إضافة منتج جديد 📦",
            body=f"تم رفع '{product.name}' بنجاح، جاري مراجعته ونشره قريباً."
        )

        messages.success(request, "تم إضافة المنتج بنجاح ✅")
        return redirect('merchant_products')

    categories = Category.objects.all()
    return render(request, 'merchant/add_product.html', {'categories': categories})


@login_required
def edit_product(request, product_id):
    """تعديل منتج موجود"""
    if not is_merchant(request.user): 
        return redirect('home')
        
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    variations = product.variations.all()
    is_simple_product = variations.count() == 1 and variations.first().color_label == 'افتراضي'

    if request.method == 'POST':
        product.name = request.POST.get('name')
        product.base_price = request.POST.get('price')
        product.description = request.POST.get('description')
        product.save()

        if is_simple_product:
            simple_qty = request.POST.get('simple_stock')
            if simple_qty is not None:
                single_var = variations.first()
                single_var.stock_quantity = simple_qty
                single_var.save()
        else:
            existing_ids = request.POST.getlist('existing_ids[]')
            for vid in existing_ids:
                qty = request.POST.get(f'qty_{vid}')
                if qty:
                    size_obj = ProductSize.objects.get(id=vid)
                    size_obj.stock_quantity = qty
                    size_obj.save()

            for key in request.POST:
                if key.startswith('new_color_group_'):
                    group_id = key.split('_')[-1]
                    color_name = request.POST.get(key)
                    sizes = request.POST.getlist(f'new_sizes_group_{group_id}[]')
                    qtys = request.POST.getlist(f'new_qtys_group_{group_id}[]')
                    
                    for i in range(len(sizes)):
                        if sizes[i] and qtys[i]:
                            ProductSize.objects.create(
                                product=product, color_label=color_name, size_label=sizes[i], stock_quantity=qtys[i]
                            )

        # --- [إشعار الداخلي] ---
        send_notification(request.user, "تم تحديث المنتج ✏️", f"تم حفظ التعديلات على المنتج '{product.name}'.", "/merchant/products/")
        
        # 🔥 --- [إشعار الموبايل Push Notification] ---
        send_push_to_user(
            user=request.user,
            title="تحديث منتج ✏️",
            body=f"تم حفظ التعديلات بنجاح على منتج '{product.name}'."
        )

        messages.success(request, "تم تحديث المنتج بنجاح ✅")
        return redirect('merchant_products')

    grouped_variations = {}
    if not is_simple_product:
        variations_by_color = defaultdict(list)
        for v in variations:
            variations_by_color[v.color_label].append(v)
        grouped_variations = dict(variations_by_color)

    return render(request, 'merchant/edit_product.html', {
        'product': product,
        'grouped_variations': grouped_variations,
        'is_simple_product': is_simple_product,
        'simple_variation': variations.first() if is_simple_product else None
    })


@login_required
def delete_product(request, product_id):
    """حذف أو أرشفة منتج"""
    if not is_merchant(request.user):
        return redirect('home')
        
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    has_orders = product.variations.filter(orderitem__isnull=False).exists()
    
    if has_orders:
        product.is_active = False 
        product.save()
        messages.warning(request, "تم إخفاء المنتج بدلاً من حذفه (لأنه موجود في طلبات سابقة).")
        
        send_notification(request.user, "أرشفة منتج 📦", f"تم إيقاف عرض '{product.name}' نظراً لارتباطه بطلبات سابقة.", "/merchant/products/")
        
        # 🔥 --- [إشعار الموبايل Push Notification] ---
        send_push_to_user(request.user, "أرشفة منتج 📦", f"تم إخفاء '{product.name}' لوجود طلبات سابقة عليه.")
    else:
        product.delete()
        messages.success(request, "تم حذف المنتج نهائياً.")
        
    return redirect('merchant_products')


@login_required
def add_offer(request, product_id):
    """إضافة عرض على منتج"""
    if not is_merchant(request.user):
        return redirect('home')
    
    product = get_object_or_404(Product, pk=product_id, merchant=request.user.merchant_profile)
    try:
        current_offer = product.active_offer
    except Offer.DoesNotExist:
        current_offer = None

    is_locked = current_offer and current_offer.is_platform_offer and current_offer.is_active
        
    if request.method == 'POST':
        if is_locked:
            messages.error(request, "عفواً، لا يمكنك تعديل عرض تم وضعه بواسطة المنصة.")
            return redirect('merchant_products')

        percentage = int(request.POST.get('percentage') or 0)
        days = int(request.POST.get('days'))
        free_shipping = request.POST.get('free_shipping') == 'on'
        threshold = int(request.POST.get('threshold', 1))
        
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
        
        send_notification(request.user, "تم إطلاق العرض 🏷️", f"تم تطبيق عرض {percentage}% على '{product.name}'.", "/merchant/products/")
        
        # 🔥 --- [إشعار الموبايل Push Notification] ---
        send_push_to_user(request.user, "إطلاق عرض جديد 🏷️", f"تم تطبيق خصم {percentage}% على '{product.name}'.")

        messages.success(request, "تم حفظ العرض ✅")
        return redirect('merchant_products')

    return render(request, 'merchant/add_offer.html', {
        'product': product, 'offer': current_offer, 'is_locked': is_locked
    })


@login_required
def cancel_offer(request, offer_id):
    """إلغاء عرض"""
    offer = get_object_or_404(Offer, pk=offer_id, product__merchant=request.user.merchant_profile)
    if offer.is_platform_offer:
        messages.error(request, "لا يمكنك إلغاء عرض المنصة.")
    else:
        offer.delete()
        messages.success(request, "تم إلغاء العرض.")
    return redirect('merchant_products')


@login_required
def merchant_orders(request):
    """عرض قائمة الطلبات الواردة للتاجر"""
    if not is_merchant(request.user): return redirect('home')
    
    excluded_statuses = [Order.Status.CART, Order.Status.WAITING_PAYMENT]
    items = OrderItem.objects.filter(
        product_size__product__merchant=request.user.merchant_profile
    ).exclude(order__status__in=excluded_statuses).order_by('-order__created_at')

    return render(request, 'merchant/orders.html', {'items': items})


@login_required
def merchant_order_detail(request, order_id):
    """عرض تفاصيل طلب محدد"""
    if not is_merchant(request.user): return redirect('home')
    
    order = get_object_or_404(Order, order_id=order_id)
    my_items = OrderItem.objects.filter(
        order=order, product_size__product__merchant=request.user.merchant_profile
    )
    
    if not my_items.exists():
        return redirect('merchant_orders')

    return render(request, 'merchant/order_detail.html', {'order': order, 'items': my_items})


@login_required
def update_order_status(request, order_id):
    """تحديث حالة الطلب وإدارة العمولات وإرسال إشعارات للعميل"""
    if not hasattr(request.user, 'merchant_profile'):
        return redirect('home')
    
    order = get_object_or_404(Order, order_id=order_id)
    merchant = request.user.merchant_profile
    
    is_owner = (order.merchant == merchant)
    has_items = order.items.filter(product_size__product__merchant=merchant).exists()
    
    if not (is_owner or has_items):
        messages.error(request, "ليس لديك صلاحية.")
        return redirect('merchant_orders')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        old_status = order.status

        # 1. حالة المرتجع (استلام التاجر للمنتج)
        if new_status == 'MERCHANT_RECEIVED_RETURN':
            order.merchant_received_return = True
            order.status = 'RETURNED' 
            order.save()
            
            send_notification(request.user, "تأكيد استلام المرتجع 📦", f"تم إثبات استلامك لمرتجع الطلب #{order.order_id}.", f"/merchant/order/{order.order_id}/")
            
            # 🔥 إشعار الموبايل للتاجر
            send_push_to_user(request.user, "استلام مرتجع 📦", f"تم تأكيد استلامك للمرتجع الخاص بالطلب #{order.order_id}.")
            
            messages.success(request, "تم تأكيد استلام المرتجع من المندوب بنجاح!")
            return redirect('merchant_order_detail', order_id=order.order_id)

        if new_status not in ['PREPARING', 'SHIPPED', 'DELIVERED', 'CANCELLED']:
            messages.error(request, "حالة غير صالحة.")
            return redirect('merchant_order_detail', order_id=order.order_id)

        # حساب عمولة المنصة
        total_commission = Decimal('0.00')
        for item in order.items.all():
            if item.product_size.product.merchant == merchant:
                pct = item.product_size.product.commission_pct / 100
                total_commission += (item.price_at_purchase * pct * Decimal(item.quantity))

        wallet = merchant.wallet
        status_changed_successfully = False

        # 2. بدء الشحن (خصم العمولة)
        if new_status == 'SHIPPED' and old_status in ['PENDING', 'PREPARING']:
            if wallet.balance < total_commission:
                messages.error(request, f"رصيدك غير كافٍ لخصم عمولة المنصة ({total_commission} ج.م). يرجى الشحن.")
                return redirect('merchant_order_detail', order_id=order.order_id)
            
            with transaction.atomic():
                order.status = 'SHIPPED'
                order.save()
                
                wallet.balance -= total_commission
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet, amount=-total_commission,
                    transaction_type='SALE', related_order_id=order.order_id,
                    description=f"خصم عمولة مبكر (شحن طلب #{order.order_id})",
                    balance_after=wallet.balance, is_released=True
                )
            
            send_notification(request.user, "تم بدء الشحن 📦", f"تم تحويل الطلب #{order.order_id} إلى جاري الشحن وخصم العمولة.", f"/merchant/order/{order.order_id}/")
            
            # 🔥 إشعار الموبايل للتاجر
            send_push_to_user(request.user, "شحن الطلب 🚚", f"تم تحويل الطلب #{order.order_id} للشحن بنجاح.")

            messages.success(request, f"تم بدء الشحن وخصم عمولة {total_commission} ج.م")
            status_changed_successfully = True

        # 3. إلغاء الطلب بعد الشحن (استرداد العمولة)
        elif new_status == 'CANCELLED' and old_status == 'SHIPPED':
            with transaction.atomic():
                order.status = 'CANCELLED'
                order.save()
                
                wallet.balance += total_commission
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet, amount=total_commission,
                    transaction_type='COMPENSATION', related_order_id=order.order_id,
                    description=f"استرداد عمولة (إلغاء شحن #{order.order_id})",
                    balance_after=wallet.balance, is_released=True
                )
            messages.warning(request, "تم إلغاء الطلب واسترداد العمولة.")
            status_changed_successfully = True

        # 4. تغيير حالة عادي (مثل جاري التحضير أو تم التسليم)
        elif new_status != old_status:
            order.status = new_status
            order.save()
            messages.success(request, f"تم تغيير الحالة إلى {order.get_status_display()}")
            status_changed_successfully = True

        # ==========================================
        # 5. [الجديد]: إرسال الإشعار للعميل بناءً على الحالة
        # ==========================================
        if status_changed_successfully:
            # قاموس رسائل الإشعارات (ديناميكي)
            customer_notifications = {
                'PREPARING': (
                    "جاري تحضير طلبك 📦", 
                    f"التاجر يقوم الآن بتجهيز طلبك رقم #{order.order_id}. سنخبرك فور شحنه!"
                ),
                'SHIPPED': (
                    "طلبك في الطريق إليك! 🚚", 
                    f"تم تسليم طلبك رقم #{order.order_id} لمندوب الشحن. استعد لاستلامه قريباً."
                ),
                'DELIVERED': (
                    "تم تسليم الطلب 🎉", 
                    f"تم تسليم طلبك رقم #{order.order_id} بنجاح. نتمنى أن ينال إعجابك!"
                ),
                'CANCELLED': (
                    "إلغاء الطلب ❌", 
                    f"نأسف، تم إلغاء طلبك رقم #{order.order_id}. يمكنك التواصل مع الدعم لمزيد من التفاصيل."
                )
            }

            if new_status in customer_notifications:
                title, msg = customer_notifications[new_status]
                try:
                    # الإشعار الداخلي للعميل
                    send_notification(
                        user=order.customer, 
                        title=title, 
                        message=msg, 
                        link="/my-orders/" 
                    )
                    
                    # 🔥 إشعار الموبايل (Push Notification) للعميل
                    send_push_to_user(
                        user=order.customer,
                        title=title,
                        body=msg
                    )
                except Exception as e:
                    print(f"Customer Notification Error: {e}")

    return redirect('merchant_order_detail', order_id=order.order_id)


@login_required
def shipping_settings(request):
    """تحديث أسعار وإعدادات الشحن للتاجر بناءً على دولته"""
    if not is_merchant(request.user):
        return redirect('home')
    
    merchant = request.user.merchant_profile
    
    # 🔥 [تعديل دولي هام]: نجلب المحافظات الخاصة بدولة التاجر فقط
    governorates = Governorate.objects.filter(country=merchant.user.country)

    if request.method == 'POST':
        for gov in governorates:
            input_name = f'rate_{gov.id}'
            price = request.POST.get(input_name)
            
            if not price or float(price) == 0:
                MerchantShippingRate.objects.filter(merchant=merchant, governorate=gov).delete()
            else:
                MerchantShippingRate.objects.update_or_create(
                    merchant=merchant, governorate=gov, defaults={'rate': price}
                )

        threshold = request.POST.get('free_shipping_threshold')
        merchant.free_shipping_threshold = int(threshold) if threshold else 0
        merchant.is_free_shipping_active = request.POST.get('is_free_shipping_active') == 'on'
        merchant.save()
        
        send_notification(request.user, "تحديث إعدادات الشحن 🚚", "تم حفظ أسعار وإعدادات الشحن بنجاح.", "/merchant/shipping/")
        
        # 🔥 إشعار الموبايل للتاجر
        send_push_to_user(request.user, "إعدادات الشحن 🚚", "تم تحديث أسعار وإعدادات الشحن لمتجرك بنجاح.")

        messages.success(request, "تم حفظ أسعار وإعدادات الشحن بنجاح ✅")
        return redirect('merchant_shipping')

    current_rates_dict = {rate.governorate_id: rate.rate for rate in merchant.shipping_rates.all()}
    shipping_data = [{'id': gov.id, 'name': gov.name, 'current_rate': current_rates_dict.get(gov.id, '')} for gov in governorates]
    
    return render(request, 'merchant/shipping_settings.html', {
        'shipping_data': shipping_data,
        'country_name': merchant.user.country.name if merchant.user.country else 'غير محدد'
    })


@login_required
def merchant_wallet(request):
    """محفظة التاجر وتحرير الأرباح التلقائي"""
    if not is_merchant(request.user): return redirect('home')
    
    wallet = request.user.merchant_profile.wallet
    settings_obj = SiteSetting.objects.first()
    release_hours = settings_obj.pending_balance_release_hours if settings_obj else 24
    
    time_threshold = timezone.now() - timedelta(hours=release_hours)
    
    pending_txs = WalletTransaction.objects.filter(
        wallet=wallet, transaction_type='PENDING',
        created_at__lte=time_threshold, is_released=False
    )
    
    released_amount = Decimal('0.00')
    if pending_txs.exists():
        with transaction.atomic():
            for tx in pending_txs:
                released_amount += tx.amount
                tx.is_released = True
                tx.transaction_type = WalletTransaction.TxType.SALE 
                tx.description += " (تم التحرير)"
                tx.save()
            
            wallet.pending_balance -= released_amount
            wallet.balance += released_amount
            wallet.save()
            
            send_notification(request.user, "تم تحرير أرباحك 💰", f"تم تحويل مبلغ {released_amount} إلى رصيدك المتاح للسحب بنجاح.", "/merchant/wallet/")
            
            # 🔥 إشعار الموبايل للتاجر
            send_push_to_user(request.user, "أرباح متاحة 💰", f"تم تحرير {released_amount} وإضافتها لرصيدك القابل للسحب.")

            messages.success(request, f"تم تحرير {released_amount} من الرصيد المعلق.")

    transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
    return render(request, 'merchant/wallet.html', {'wallet': wallet, 'transactions': transactions})


@login_required
def request_withdrawal(request):
    """طلب سحب رصيد متاح"""
    if not is_merchant(request.user): return redirect('home')
    
    wallet = request.user.merchant_profile.wallet
    settings_obj = SiteSetting.objects.first()
    
    min_withdraw_amount = settings_obj.min_withdrawal_amount if settings_obj else Decimal('50.00')
    reserved_balance = settings_obj.min_wallet_balance if settings_obj else Decimal('200.00')
    
    withdrawable_balance = max(Decimal('0.00'), wallet.balance - reserved_balance)

    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount'))
            phone = request.POST.get('phone')
            
            if amount > withdrawable_balance:
                messages.error(request, f"رصيدك غير كافٍ. يجب إبقاء {reserved_balance} في المحفظة.")
            elif amount < min_withdraw_amount:
                messages.error(request, f"أقل مبلغ يمكن سحبه هو {min_withdraw_amount}")
            else:
                with transaction.atomic():
                    WithdrawalRequest.objects.create(merchant=request.user.merchant_profile, amount=amount, phone_number=phone)
                    wallet.balance -= amount
                    wallet.save()
                    WalletTransaction.objects.create(
                        wallet=wallet, amount=-amount, transaction_type=WalletTransaction.TxType.WITHDRAWAL,
                        description="طلب سحب (قيد المراجعة)", balance_after=wallet.balance, is_released=False 
                    )

                send_notification(request.user, "طلب سحب أرباح 💸", f"تم استلام طلب سحب بمبلغ {amount} وجاري مراجعته من الإدارة.", "/merchant/wallet/")
                
                # 🔥 إشعار الموبايل للتاجر
                send_push_to_user(request.user, "تم استلام طلب السحب 💸", f"طلب سحب بقيمة {amount} قيد المراجعة الآن.")

                messages.success(request, "تم تقديم طلب السحب بنجاح. سيتم تحويل المبلغ قريباً.")
                return redirect('merchant_wallet')

        except Exception as e:
            messages.error(request, "حدث خطأ في البيانات. يرجى المحاولة مرة أخرى.")

    return render(request, 'merchant/withdraw.html', {
        'wallet': wallet, 'withdrawable_balance': withdrawable_balance,
        'min_withdraw': min_withdraw_amount, 'reserved_balance': reserved_balance
    })


@login_required
def paymob_deposit(request):
    """شحن المحفظة برصيد (مع إضافة رسوم Paymob)"""
    if not is_merchant(request.user): return redirect('home')

    settings_obj = SiteSetting.objects.first()
    fee_fixed = float(settings_obj.platform_fee_fixed) if settings_obj else 0.0
    fee_percent = float(settings_obj.platform_fee_percentage) if settings_obj else 0.0

    if request.method == 'POST':
        try:
            net_amount = float(request.POST.get('amount'))
            method = request.POST.get('method')
            
            if net_amount < 10:
                messages.error(request, "الحد الأدنى للشحن 10 ج.م")
                return redirect('paymob_deposit')

            total_fees = fee_fixed + (net_amount * (fee_percent / 100.0))
            total_to_pay = net_amount + total_fees
            amount_cents = int(total_to_pay * 100)
            
            paymob = PaymobManager()
            token = paymob.get_token()
            pm_order_id = paymob.create_order(token, amount_cents)
            
            PaymobTransaction.objects.create(
                merchant=request.user.merchant_profile,
                paymob_order_id=str(pm_order_id), amount_cents=amount_cents, is_paid=False
            )

            user = request.user
            billing_data = {
                "first_name": user.first_name or "Merchant", "last_name": user.last_name or "User",
                "email": user.email or "merchant@bazarna.com", "phone_number": user.phone_primary,
                "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA", 
                "shipping_method": "NA", "postal_code": "NA", "city": "Cairo", "country": "EG", "state": "NA"
            }

            if method == 'WALLET':
                wallet_num = request.POST.get('wallet_number')
                if not wallet_num:
                    messages.error(request, "رقم المحفظة مطلوب.")
                    return redirect('paymob_deposit')
                billing_data['phone_number'] = wallet_num
                redirect_url = paymob.pay_with_wallet(token, amount_cents, pm_order_id, settings.PAYMOB_INTEGRATION_ID_WALLET, billing_data)
                return redirect(redirect_url)
            else:
                payment_key = paymob.get_payment_key(token, pm_order_id, amount_cents, settings.PAYMOB_INTEGRATION_ID_CARD, billing_data)
                iframe_url = f"https://accept.paymob.com/api/acceptance/iframes/{settings.PAYMOB_IFRAME_ID}?payment_token={payment_key}"
                return render(request, 'store/paymob_iframe.html', {'iframe_url': iframe_url})

        except Exception as e:
            messages.error(request, "حدث خطأ أثناء الاتصال ببوابة الدفع.")
            return redirect('merchant_wallet')

    return render(request, 'merchant/paymob_deposit.html', {'fee_fixed': fee_fixed, 'fee_percent': fee_percent})


def paymob_callback(request):
    """الرد الآلي من Paymob بعد الدفع"""
    success = request.GET.get('success')
    order_id = request.GET.get('order')
    
    if success == "true":
        try:
            tx = PaymobTransaction.objects.get(paymob_order_id=order_id, is_paid=False)
            tx.is_paid = True
            tx.save()
            
            wallet = tx.merchant.wallet
            
            # حساب الصافي بعد خصم الرسوم
            settings_obj = SiteSetting.objects.first()
            fixed_fee = Decimal(settings_obj.platform_fee_fixed) if settings_obj else Decimal('0.00')
            percent_fee = Decimal(settings_obj.platform_fee_percentage) / Decimal('100.00') if settings_obj else Decimal('0.00')
            
            total_paid = Decimal(tx.amount_cents) / 100
            net_amount = round((total_paid - fixed_fee) / (Decimal('1.00') + percent_fee), 2)
            if net_amount < Decimal('0.00'): net_amount = Decimal('0.00')
                
            fees_deducted = total_paid - net_amount

            WalletTransaction.objects.create(
                wallet=wallet, amount=net_amount, transaction_type=WalletTransaction.TxType.COMPENSATION,
                description=f"شحن رصيد (Paymob) #{tx.id} (خصم {fees_deducted} ج.م رسوم)", balance_after=wallet.balance + net_amount
            )
            
            wallet.balance += net_amount
            wallet.save()
            
            send_notification(tx.merchant.user, "تم شحن الرصيد بنجاح! 💰", f"تم شحن محفظتك بصافي {net_amount} بعد خصم رسوم البنك.", "/merchant/wallet/")
            
            # 🔥 إشعار الموبايل للتاجر بنجاح الشحن
            send_push_to_user(tx.merchant.user, "شحن المحفظة 💳", f"تم إيداع مبلغ {net_amount} في محفظتك بنجاح.")

            messages.success(request, f"تم شحن الرصيد بنجاح! 🎉 (صافي: {net_amount})")
            return redirect('merchant_wallet')
            
        except PaymobTransaction.DoesNotExist:
            return redirect('merchant_wallet')
    else:
        messages.error(request, "عملية الدفع فشلت أو تم إلغاؤها.")
        return redirect('merchant_wallet')


@login_required
def merchant_reports(request):
    """التقارير والإحصائيات للتاجر"""
    if not hasattr(request.user, 'merchant_profile'): 
        return redirect('home')
    
    merchant = request.user.merchant_profile
    wallet = merchant.wallet

    range_type = request.GET.get('range', 'month')
    custom_start = request.GET.get('start')
    custom_end = request.GET.get('end')
    
    today = timezone.now().date()
    start_date = today.replace(day=1)
    end_date = today

    if range_type == 'today': start_date = today
    elif range_type == 'week': start_date = today - timedelta(days=7)
    elif range_type == 'month': start_date = today.replace(day=1)
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
        order__created_at__date__gte=start_date,
        order__created_at__date__lte=end_date
    )

    total_sales = sold_items.aggregate(
        total=Sum(F('quantity') * F('price_at_purchase'))
    )['total'] or Decimal('0.00')

    total_orders = Order.objects.filter(
        merchant=merchant,
        status__in=valid_order_statuses,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).count()

    total_returned_orders = Order.objects.filter(
        merchant=merchant,
        status='RETURNED',
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).count()

    returned_items = OrderItem.objects.filter(
        product_size__product__merchant=merchant,
        order__status='RETURNED',
        order__created_at__date__gte=start_date,
        order__created_at__date__lte=end_date
    )
    
    total_returned_value = returned_items.aggregate(
        total=Sum(F('quantity') * F('price_at_purchase'))
    )['total'] or Decimal('0.00')

    top_products = OrderItem.objects.filter(
        product_size__product__merchant=merchant, 
        order__status='DELIVERED',
        order__created_at__date__gte=start_date, 
        order__created_at__date__lte=end_date
    ).values('product_size__product__name').annotate(
        total_qty=Sum('quantity'), 
        total_revenue=Sum(F('quantity') * F('price_at_purchase'))
    ).order_by('-total_qty')[:5]

    trunc_func = TruncMonth if range_type == 'year' else TruncDay
    fmt = "%b" if range_type == 'year' else "%d %b"
    
    chart_data = sold_items.annotate(
        period=trunc_func('order__created_at')
    ).values('period').annotate(
        total=Sum(F('quantity') * F('price_at_purchase'))
    ).order_by('period')
    
    labels, values = [], []
    for item in chart_data:
        if item['period']:
            labels.append(item['period'].strftime(fmt))
            values.append(float(item['total']))

    if not labels:
        labels, values = ["لا توجد بيانات"], [0]

    context = {
        'total_sales': float(total_sales), 
        'total_orders': total_orders,
        'total_returned_orders': total_returned_orders,  
        'total_returned_value': float(total_returned_value), 
        'top_products': top_products, 
        'chart_labels': json.dumps(labels), 
        'chart_values': json.dumps(values),
        'current_range': range_type, 
        'start_date': start_date, 
        'end_date': end_date
    }
    
    return render(request, 'merchant/reports.html', context)

from django.db.models import Q
from store.models import TermsAndCondition # تأكد من مسار الموديل الصحيح

@login_required
def merchant_profile(request):
    """عرض صفحة حساب التاجر مع السياسات الديناميكية"""
    if not hasattr(request.user, 'merchant_profile'):
        return redirect('home')
        
    merchant = request.user.merchant_profile
    current_country = request.user.country
    
    # 🔥 جلب السياسات الخاصة بالتجار بناءً على الدولة (أو السياسات العامة التي لا ترتبط بدولة معينة)
    merchant_policies = TermsAndCondition.objects.filter(
        user_type='MERCHANT',
        is_active=True
    ).filter(
        Q(country=current_country) | Q(country__isnull=True)
    ).order_by('order')
    
    # تقسيم السياسات حسب النوع
    terms_list = merchant_policies.filter(document_type='TERMS')
    privacy_list = merchant_policies.filter(document_type='PRIVACY')
    shipping_list = merchant_policies.filter(document_type='SHIPPING_RETURN')
    
    context = {
        'merchant': merchant,
        'terms_list': terms_list,
        'privacy_list': privacy_list,
        'shipping_list': shipping_list,
    }
    
    return render(request, 'merchant/profile.html', context)