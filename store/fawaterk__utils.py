import requests
import re
from django.conf import settings

class FawaterkManager:
    def __init__(self):
        self.api_key = settings.FAWATERK_API_KEY
        self.base_url = "https://staging.fawaterk.com/api/v2" 

    def create_invoice(self, cart_total, customer_data, cart_items, order_id, is_wallet_deposit=False):
        """إنشاء فاتورة والحصول على رابط الدفع من فواتيرك"""
        url = f"{self.base_url}/createInvoiceLink"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # 1. تقريب الرقم لضمان عدم رفض فواتيرك للكسور الطويلة
        safe_total = round(float(cart_total), 2)
        item_name = f"Order {order_id}" if not is_wallet_deposit else f"Wallet Deposit {order_id}"
        
        items_payload = [{
            "name": item_name,
            "price": safe_total,
            "quantity": 1
        }]

        # 🔥 2. التنظيف الإجباري لبيانات العميل (مضاد لرفض فواتيرك)
        # إزالة أي أرقام أو رموز من الأسماء باستخدام (Regex)، والاحتفاظ بالحروف والمسافات فقط
        f_name = re.sub(r'[^a-zA-Z\u0600-\u06FF\s]', '', str(customer_data.get('first_name', ''))).strip()
        l_name = re.sub(r'[^a-zA-Z\u0600-\u06FF\s]', '', str(customer_data.get('last_name', ''))).strip()
        
        # التأكد من أن الاسم حرفين على الأقل لتجنب الرفض
        if len(f_name) < 2: f_name = 'Client'
        if len(l_name) < 2: l_name = 'User'

        # تنظيف الإيميل والهاتف
        email = customer_data.get('email', '')
        if not email or '@' not in email: 
            email = 'info@elbazaare.com'
            
        phone = customer_data.get('phone', '')
        if not phone or len(str(phone)) < 8: 
            phone = '01000000000'

        data = {
            "cartTotal": safe_total,
            "currency": "EGP",
            "customer": {
                "first_name": f_name[:20],
                "last_name": l_name[:20],
                "email": email,
                "phone": str(phone),
                "address": str(customer_data.get('address', 'Egypt'))[:50]
            },
            "cartItems": items_payload,
            "sendEmail": False, # منع فواتيرك من إرسال إيميلات مزعجة للعميل أو الرفض لو الإيميل وهمي
            "returnUrl": settings.FAWATERK_SUCCESS_URL,
            "callbackUrl": settings.FAWATERK_WEBHOOK_URL,
            "metadata": {
                "system_order_id": str(order_id),
                "is_wallet_deposit": "true" if is_wallet_deposit else "false"
            }
        }
        
        try:
            response = requests.post(url, json=data, headers=headers)
            res_data = response.json()
            
            if res_data.get('status') == 'success':
                return True, res_data['data']
            
            error_msg = res_data.get('message', 'مرفوض من فواتيرك')
            if 'errors' in res_data:
                error_msg += f" - {res_data['errors']}"
            return False, error_msg
            
        except Exception as e:
            return False, f"خطأ في الاتصال: {str(e)}"
            
    def get_transaction_data(self, invoice_id):
        """جلب تفاصيل الفاتورة من فواتيرك للتأكد من الدفع الفعلي"""
        url = f"{self.base_url}/getInvoiceData/{invoice_id}"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers)
            res_data = response.json()
            if res_data.get('status') == 'success':
                return True, res_data.get('data', {})
            return False, {}
        except:
            return False, {}