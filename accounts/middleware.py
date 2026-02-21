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