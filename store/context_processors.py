from .models import SiteSetting # تأكد من النقطة
from accounts.models import Country
from support.models import SupportTicket
from .models import ReturnRequest
from django.utils import timezone
from .models import PromoPopup


def site_settings(request):
    settings = SiteSetting.objects.first()
    return {'site_settings': settings}

 

def global_country_context(request):
    has_country = False
    
    if request.user.is_authenticated and request.user.country:
        has_country = True
    elif request.session.get('user_country_id'):
        has_country = True

    return {
        'user_has_country': has_country,
        'available_countries': Country.objects.filter(is_active=True)
    }

def admin_notifications_processor(request):
    context = {'open_tickets_count': 0, 'pending_returns_count': 0}
    
    if request.user.is_authenticated and request.user.role in ['ADMIN_LVL3', 'OWNER']:
        # عداد التذاكر
        context['open_tickets_count'] = SupportTicket.objects.filter(status=SupportTicket.Status.OPEN).count()
        
        # عداد المرتجعات الجديدة
        context['pending_returns_count'] = ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count()
        
    return context


def active_promo_popup(request):
    now = timezone.now()
    promo = PromoPopup.objects.filter(
        is_active=True, 
        start_time__lte=now,  
        end_time__gt=now      
    ).first()
    
    return {'active_promo': promo}



