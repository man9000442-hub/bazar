from .models import SupportTicket
from store.models import DeliveryComplaint,ReturnRequest

def support_tickets_processor(request):
    # نتأكد أن المستخدم مسجل الدخول (ويمكنك إضافة شرط الصلاحية لاحقاً إذا أردت)
    if request.user.is_authenticated:
        # هنا استخدمنا اسم الموديل الصحيح SupportTicket
        count = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count()
        return {'open_tickets_count': count}
    
    return {'open_tickets_count': 0}


def support_tickets_processor(request):
    context = {'open_tickets_count': 0, 'new_complaints_count': 0}
    
    if request.user.is_authenticated and request.user.role in ['ADMIN_LVL3', 'OWNER']:
        context['open_tickets_count'] = SupportTicket.objects.filter(status='OPEN').count()
        
        # عداد شكاوى التسليم التي لم تُحل بعد
        context['new_complaints_count'] = DeliveryComplaint.objects.filter(is_resolved=False).count()
        
    return context


from .models import SupportTicket # تأكد من إضافة ReturnRequest

def admin_notifications_processor(request):
    context = {'open_tickets_count': 0, 'pending_returns_count': 0}
    
    if request.user.is_authenticated and request.user.role in ['ADMIN_LVL3', 'OWNER']:
        # عداد التذاكر
        context['open_tickets_count'] = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count()
        
        # عداد المرتجعات الجديدة
        context['pending_returns_count'] = ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count()
        
    return context