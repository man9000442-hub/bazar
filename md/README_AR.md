# Bazarna - التوثيق الشامل

> منصة تجارة إلكترونية متعددة الدول وموثوقة لإدارة الأسواق العالمية

---

## 📖 جدول المحتويات

- [نظرة عامة](#نظرة-عامة)
- [البدء السريع](#البدء-السريع)
- [الوثائق الرئيسية](#الوثائق-الرئيسية)
- [دليل المطورين](#دليل-المطورين)
- [الدعم والمساهمة](#الدعم-والمساهمة)

---

## نظرة عامة

**Bazarna** هي منصة تجارة إلكترونية حديثة مبنية بـ **Django 6.0** وموجهة للعمل في أسواق متعددة حول العالم.

### الميزات الرئيسية

✅ **نظام متعدد الدول** - دعم كامل لإدارة أسواق منفصلة في دول مختلفة  
✅ **أدوار وصلاحيات متقدمة** - 6 أدوار مع فلترة ذكية حسب الدول  
✅ **معالجة الدفع** - تكامل مع Paymob و Fawaterk  
✅ **إدارة المنتجات** - مع مقاسات وألوان وعروض  
✅ **نظام المحافظ الرقمية** - لإدارة رصيد التجار  
✅ **نظام الدعم الفني** - تذاكر وتتبع المشاكل  
✅ **نظام التقييمات** - من المستخدمين للمنتجات

### التقنيات المستخدمة

- **Backend**: Django 6.0, Python 3.10+
- **Database**: PostgreSQL (الإنتاج), SQLite (التطوير)
- **Frontend**: HTML5, CSS3, JavaScript
- **API**: Django REST Framework with JWT
- **الخادم**: Gunicorn + Nginx
- **المصادقة**: Email, Phone, Google OAuth

---

## البدء السريع

### المتطلبات

```bash
Python >= 3.10
PostgreSQL >= 12 (للإنتاج)
Node.js >= 14 (اختياري)
```

### التثبيت

```bash
# 1. استنساخ المستودع
git clone https://github.com/U-WWW/bazar.git
cd bazarna

# 2. إنشاء بيئة افتراضية
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. تثبيت المكتبات
pip install -r requirements.txt

# 4. إعداد قاعدة البيانات
cp .env.example .env
python manage.py migrate

# 5. إنشاء مستخدم أساسي
python manage.py createsuperuser

# 6. تشغيل الخادم
python manage.py runserver
```

الآن يمكنك الوصول إلى الموقع على `http://localhost:8000`

---

## الوثائق الرئيسية

### 1. 📘 [ملخص المشروع الشامل](./PROJECT_SUMMARY_AR.md)

وثيقة تفصيلية تغطي:

- البنية المعمارية الكاملة
- نظام الدول والأدوار
- الموديلات وقاعدة البيانات
- العمليات والحسابات
- التكاملات الخارجية

**مثالي لـ:** فهم المشروع بشكل عام

---

### 2. 📋 [سجل التغييرات](./CHANGELOG_AR.md)

توثيق شامل للتحديثات:

- الميزات الجديدة
- الأخطاء المصححة
- التغييرات التقنية
- ملفات معدلة
- خطوات التطبيق

**مثالي لـ:** متابعة التطور والمساهمة

---

### 3. 🚀 [دليل الترقية والتطور](./MIGRATION_GUIDE_AR.md)

رحلة المشروع من v1.0 إلى v2.0:

- مراحل التطور
- كيفية إضافة دول جديدة
- أمثلة عملية وحالات استخدام
- حلول للتحديات

**مثالي لـ:** التوسع والإضافة

---

### 4. 📚 [فهرس الوثائق](./DOCUMENTATION_INDEX_AR.md)

دليل شامل للملفات والموارد:

- دليل القراءة حسب الدور
- البحث السريع
- الإحصائيات

**مثالي لـ:** الملاحة والبحث

---

## دليل المطورين

### الهيكل العام للمشروع

```
bazarna/
├── accounts/              # 👥 المستخدمون والمصادقة
│   ├── models.py         # Country, User, CustomRole
│   ├── views.py
│   ├── api_views.py      # REST endpoints
│   └── ...
├── store/                 # 🛍️ المتجر والمنتجات
│   ├── models.py         # Product, Order, Wallet
│   ├── views.py
│   ├── services.py       # منطق العمليات
│   └── ...
├── merchant_panel/        # 🏪 لوحة التاجر
├── supervisor/            # 👨‍💼 لوحة الإدارة
├── support/               # 🆘 الدعم الفني
├── templates/             # 📄 القوالب
├── static/                # 🎨 الملفات الثابتة
├── manage.py              # أداة Django
└── requirements.txt       # المكتبات
```

### قواعد الكود

#### 1. النماذج (Models)

```python
# ✅ صحيح
class Product(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, verbose_name="اسم المنتج")

    class Meta:
        verbose_name = "منتج"
        ordering = ['-created_at']

# ❌ خطأ
class Product(models.Model):
    name = models.CharField(max_length=200)  # بدون country
```

#### 2. الـ Views

```python
# ✅ صحيح - مع فلترة الدولة
def product_list(request):
    country_filter = get_country_kwargs(request.user)
    products = Product.objects.filter(**country_filter)
    return render(request, 'products.html', {'products': products})

# ❌ خطأ - بدون فلترة
def product_list(request):
    products = Product.objects.all()  # يعرض كل المنتجات
    return render(request, 'products.html', {'products': products})
```

#### 3. الاستعلامات

```python
# ✅ صحيح - مع select_related
products = Product.objects.select_related(
    'category',
    'merchant'
).filter(is_active=True)

# ❌ خطأ - N+1 queries
products = Product.objects.filter(is_active=True)
for product in products:
    print(product.category.name)  # query لكل منتج
```

### سير العمل (Workflow)

#### إضافة ميزة جديدة

```bash
# 1. إنشاء branch جديد
git checkout -b feature/new-feature

# 2. تطوير الميزة
# - عدّل الموديلات
# - اكتب الـ views و serializers
# - أنشئ الاختبارات
# - حدّث الوثائق

# 3. تشغيل الاختبارات
python manage.py test

# 4. commit المغيرات
git add .
git commit -m "feat: add new feature"

# 5. push والـ pull request
git push origin feature/new-feature
# ثم أنشئ PR على GitHub
```

#### إضافة دولة جديدة

```bash
python manage.py shell
```

```python
from accounts.models import Country
from store.models import Governorate, SiteSetting

# 1. إنشاء الدولة
egypt = Country.objects.create(
    name="مصر",
    code="EG",
    phone_code="+20",
    currency_name="جنيه مصري",
    currency_symbol="ج.م",
    is_active=True,
    paymob_integration_id_card="123456",
    paymob_integration_id_wallet="654321"
)

# 2. إضافة المحافظات
Governorate.objects.bulk_create([
    Governorate(country=egypt, name="القاهرة"),
    Governorate(country=egypt, name="الجيزة"),
])

# 3. إضافة الإعدادات
SiteSetting.objects.create(
    country=egypt,
    site_name="بازار مصر",
    platform_fee_fixed=3.00,
    platform_fee_percentage=2.75,
)

exit()
```

---

## الدعم والمساهمة

### الإبلاغ عن الأخطاء

إذا وجدت خطأ، يرجى:

1. تفقد [Issues](https://github.com/U-WWW/bazar/issues) الموجودة
2. أنشئ issue جديدة مع:
   - وصف واضح للمشكلة
   - خطوات التكرار
   - ملقطات الشاشة (إذا لزم)

### طلب ميزات جديدة

1. اذهب إلى [Discussions](https://github.com/U-WWW/bazar/discussions)
2. اشرح الميزة المطلوبة
3. اشرح الفائدة المتوقعة

### المساهمة

نرحب بمساهماتك! يرجى:

1. اتبع [قواعد الكود](#قواعس-الكود)
2. أضف اختبارات لأي ميزة جديدة
3. حدّث الوثائق
4. أنشئ Pull Request مع وصف واضح

---

## الموارد الإضافية

### الملفات المهمة

```
.env                    # المتغيرات البيئية (سري)
requirements.txt        # المكتبات المطلوبة
Procfile               # تعريفات العمليات
runtime.txt            # إصدار Python
```

### الروابط المفيدة

- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [PostgreSQL Docs](https://www.postgresql.org/docs/)
- [Paymob API](https://docs.paymob.com/)

### الاتصال

- **البريد الإلكتروني**: support@bazarna.com
- **WhatsApp**: +20 1234 567890 (الدعم الفني)
- **الموقع**: https://elbazaare.com

---

## الترخيص

هذا المشروع مرخص تحت رخصة MIT. اقرأ [LICENSE](./LICENSE) للتفاصيل.

---

## شكر وتقدير

شكراً لجميع المساهمين والداعمين الذين ساعدوا في تطوير هذا المشروع.

---

**آخر تحديث:** أبريل 21، 2026  
**الإصدار:** 2.0.0 (Multi-Country Release)  
**الحالة:** ✅ منتج
