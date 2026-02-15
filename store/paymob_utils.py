import requests
from django.conf import settings

class PaymobManager:
    def __init__(self):
        self.api_key = settings.PAYMOB_API_KEY
    
    def get_token(self):
        """1. الحصول على التوكن"""
        url = "https://accept.paymob.com/api/auth/tokens"
        resp = requests.post(url, json={"api_key": self.api_key})
        return resp.json().get('token')

    def create_order(self, token, amount_cents):
        """2. إنشاء طلب دفع"""
        url = "https://accept.paymob.com/api/ecommerce/orders"
        data = {
            "auth_token": token,
            "delivery_needed": "false",
            "amount_cents": amount_cents,
            "currency": "EGP",
            "items": []
        }
        resp = requests.post(url, json=data)
        return resp.json().get('id')

    def get_payment_key(self, token, order_id, amount_cents, integration_id, billing_data):
        """3. الحصول على مفتاح الدفع"""
        url = "https://accept.paymob.com/api/acceptance/payment_keys"
        data = {
            "auth_token": token,
            "amount_cents": amount_cents,
            "expiration": 3600,
            "order_id": order_id,
            "billing_data": billing_data,
            "currency": "EGP",
            "integration_id": integration_id
        }
        resp = requests.post(url, json=data)
        return resp.json().get('token')