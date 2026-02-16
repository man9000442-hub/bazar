from .models import SiteSetting

def site_settings(request):
    settings = SiteSetting.objects.first()
    return {'site_settings': settings}