import requests
from django.conf import settings

class FawaterkManager:
    def __init__(self):
        # يفضل وضع الرابط في settings.py أيضاً
        # للمود الحي (Live): https://app.fawaterk.com/api/v2
        self.api_key = settings.FAWATERK_API_KEY
        self.base_url = "https://staging.fawaterk.com/api/v2" 

    def create_invoice(self, cart_total, customer_data, cart_items, order_id, is_wallet_deposit=False):
        """إنشاء فاتورة والحصول على رابط الدفع"""
        url = f"{self.base_url}/createInvoiceLink"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # تحضير بيانات المنتجات لفواتيرك
        items_payload = []
        for item in cart_items:
            items_payload.append({
                "name": item.get('name', 'Product'),
                "price": float(item.get('price', 0)),
                "quantity": int(item.get('quantity', 1))
            })

        data = {
            "payment_method_id": 2, # 2 للفيزا، 3 للمحافظ
            "cartTotal": float(cart_total),
            "currency": "EGP",
            "customer": {
                "first_name": customer_data.get('first_name'),
                "last_name": customer_data.get('last_name'),
                "email": customer_data.get('email'),
                "phone": customer_data.get('phone'),
                "address": customer_data.get('address')
            },
            "cartItems": items_payload,
            "sendEmail": True,
            "returnUrl": settings.FAWATERK_SUCCESS_URL, # رابط العودة بعد النجاح
            "callbackUrl": settings.FAWATERK_WEBHOOK_URL, # رابط الـ Webhook
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
            return False, res_data.get('message', 'Error from Fawaterk')
        except Exception as e:
            return False, str(e)
        
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
                return True, res_data['data']
            return False, res_data.get('message', 'Error fetching data')
        except Exception as e:
            return False, str(e)