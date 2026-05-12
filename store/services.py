from decimal import Decimal
from store.models import MerchantShippingRate, SiteSetting

class OrderService:
    """
    طبقة الخدمات المركزية (Services Layer).
    أي عملية حسابية معقدة تخص الطلبات توضع هنا لمنع تكرار الكود.
    """

    @staticmethod
    def calculate_merchant_shipping(merchant, governorate, items, is_first_order=False, has_free_voucher=False):
        """
        حساب تكلفة الشحن لتاجر معين بناءً على المحافظة والمنتجات والعروض.
        """
        rate_obj = MerchantShippingRate.objects.filter(merchant=merchant, governorate=governorate).first()
        base_shipping = rate_obj.rate if rate_obj else Decimal('50.00')
        extra_shipping = sum(i.product_size.product.shipping_fee * i.quantity for i in items)
        
        is_free_offer = False
        for item in items:
            try:
                off = item.product_size.product.active_offer
                if off and off.is_active and off.free_shipping and item.quantity >= off.free_shipping_threshold:
                    is_free_offer = True
                    break
            except: pass

        cost = base_shipping + extra_shipping
        
        # تطبيق الشحن المجاني لو متاح
        if is_free_offer or has_free_voucher or is_first_order:
            cost = Decimal('0.00')
            
        return cost, is_free_offer

    @staticmethod
    def calculate_gateway_fees(amount, country):
        """
        حساب رسوم بوابات الدفع (Paymob / Fawaterk) بناءً على إعدادات الدولة.
        """
        settings_obj = SiteSetting.get_settings(country)
        if not settings_obj:
            return Decimal('0.00')
            
        fixed = Decimal(str(settings_obj.platform_fee_fixed))
        percent = Decimal(str(settings_obj.platform_fee_percentage)) / Decimal('100.0')
        
        fees = fixed + (Decimal(str(amount)) * percent)
        return round(fees, 2)
    @staticmethod
    def apply_merchant_cashback(order):
        """
        حساب الكاش باك للتاجر وإضافته للمحفظة المعلقة عند نجاح تسليم الطلب
        """
        from store.models import WalletTransaction, MerchantCashback
        
        if order.status != 'DELIVERED':
            return False
            
        try:
            # نجلب قاعدة الكاش باك لو موجودة وصالحة
            cashback_rule = order.merchant.cashback_rule
            if not cashback_rule.is_valid_now():
                return False
        except Exception: # لو التاجر ملوش كاش باك أو الموديل مش موجود
            return False
            
        wallet = order.merchant.wallet
        
        # نحسب قيمة الكاش باك
        if cashback_rule.cashback_type == 'PERCENTAGE':
            cashback_amount = (order.total_products_price * cashback_rule.amount) / Decimal('100.0')
        else:
            cashback_amount = cashback_rule.amount
            
        if cashback_amount > 0:
            # إضافة الرصيد المعلق
            wallet.pending_balance += cashback_amount
            wallet.save()
            
            # تسجيل العملية
            WalletTransaction.objects.create(
                wallet=wallet,
                amount=cashback_amount,
                transaction_type='PENDING', 
                related_order_id=order.order_id,
                description=f"🎁 مكافأة كاش باك عن الطلب #{order.order_id}",
                balance_after=wallet.balance, # الرصيد المتاح لا يتأثر لأنها معلقة
                is_released=False
            )
            
            # إشعار التاجر بالمكافأة
            from store.utils import send_notification, send_push_to_user
            send_notification(
                user=order.merchant.user,
                title="مكافأة كاش باك! 🎁",
                message=f"تمت إضافة {cashback_amount} ج.م كرصيد معلق مكافأة على نجاح الطلب #{order.order_id}.",
                link="/merchant/wallet/"
            )
            send_push_to_user(order.merchant.user, "كاش باك نزل حسابك! 🎁", f"كسبت {cashback_amount} ج.م كاش باك من الإدارة.")
            return True
            
        return False