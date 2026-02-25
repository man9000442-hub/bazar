from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Product

# 1. خريطة المنتجات (Dynamic)
class ProductSitemap(Sitemap):
    changefreq = "daily"  # التردد المتوقع للتغيير
    priority = 0.9        # الأهمية (من 0 إلى 1)

    def items(self):
        # نرسل لجوجل المنتجات المفعلة فقط
        return Product.objects.filter(is_active=True).order_by('-created_at')

    def location(self, obj):
        return reverse('product_detail', args=[obj.pk])

    def lastmod(self, obj):
        return obj.created_at

# 2. خريطة الصفحات الثابتة (Static)
class StaticSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        # نضع أسماء الروابط الموجودة في urls.py بدقة
        return ['home', 'account_login', 'signup_choice'] 

    def location(self, item):
        return reverse(item)