from django.shortcuts import render, redirect
from django.urls import reverse

class BanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_banned:
            
            # قائمة المسارات المسموح بها للمحظور
            allowed_paths = [
                reverse('account_logout'),
                reverse('my_tickets'),
                reverse('create_ticket'),
            ]
            
            # السماح بالدخول لصفحة تفاصيل التذكرة (لأن الرابط متغير)
            # مثال: /support/15/
            is_ticket_detail = request.path.startswith('/support/')
            
            # إذا لم يكن في صفحة مسموحة -> وجهه لصفحة الحظر
            if request.path not in allowed_paths and not is_ticket_detail:
                return render(request, 'account/banned.html')

        response = self.get_response(request)
        return response
    

from django.shortcuts import redirect
from django.urls import reverse

class MerchantApprovalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. نتأكد إن المستخدم مسجل دخول وهو تاجر
        if request.user.is_authenticated and getattr(request.user, 'role', '') == 'MERCHANT':
            
            # 2. الروابط المستثناة عشان ميعملش (Infinite Redirect Loop)
            allowed_urls = [
                reverse('merchant_pending_approval'),
                reverse('logout'),
            ]
            
            # 3. لو بيحاول يفتح أي رابط غير المسموحين، ولوحة الإدمن كمان
            if request.path not in allowed_urls and not request.path.startswith('/admin/'):
                try:
                    # 4. لو التاجر غير مفعل (is_approved = False)، اطرده لصفحة المراجعة
                    if not request.user.merchant_profile.is_approved:
                        return redirect('merchant_pending_approval')
                except Exception as e:
                    # لو حصل مشكلة (مثلاً معندوش بروفايل تاجر أصلاً)
                    pass
                    
        response = self.get_response(request)
        return response