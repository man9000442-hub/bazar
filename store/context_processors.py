from .models import SiteSetting # تأكد من النقطة

def site_settings(request):
    # استخدم first() لتجنب الأخطاء لو الجدول فارغ
    settings = SiteSetting.objects.first()
    return {'site_settings': settings}


from support.models import SupportTicket
from .models import ReturnRequest # تأكد من إضافة ReturnRequest

def admin_notifications_processor(request):
    context = {'open_tickets_count': 0, 'pending_returns_count': 0}
    
    if request.user.is_authenticated and request.user.role in ['ADMIN_LVL3', 'OWNER']:
        # عداد التذاكر
        context['open_tickets_count'] = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count()
        
        # عداد المرتجعات الجديدة
        context['pending_returns_count'] = ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count()
        
    return context


from django.utils import timezone
from .models import PromoPopup

from django.utils import timezone
from .models import PromoPopup

from .models import PromoPopup

from django.utils import timezone
from .models import PromoPopup

def active_promo_popup(request):
    now = timezone.now()
    # السيستم هيجيب الإعلان المفعل + اللي وقت بدايته جه + ووقت نهايته لسه مجاش
    promo = PromoPopup.objects.filter(
        is_active=True, 
        start_time__lte=now,  
        end_time__gt=now      
    ).first()
    
    return {'active_promo': promo}

