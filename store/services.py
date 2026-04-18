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