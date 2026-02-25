from .models import SiteSetting # تأكد من النقطة

def site_settings(request):
    # استخدم first() لتجنب الأخطاء لو الجدول فارغ
    settings = SiteSetting.objects.first()
    return {'site_settings': settings}