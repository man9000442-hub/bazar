# دليل الترقية والتطور

> كيفية الانتقال من إصدار إلى آخر وإضافة ميزات جديدة

---

## نظرة عامة

هذا الدليل يوضح:

- كيفية ترقية الإصدارات
- كيفية إضافة دول جديدة
- كيفية استخدام الميزات الجديدة
- أفضل الممارسات

---

## الترقية من v1.0 إلى v2.0

### الخطوة 1: تحديث الكود

```bash
# تنزيل الإصدار الجديد
git pull origin main

# أو من التاريخ المحدد
git checkout v2.0.0
```

### الخطوة 2: تثبيت المكتبات

```bash
pip install -r requirements.txt --upgrade
```

### الخطوة 3: تشغيل Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### الخطوة 4: إعادة التشغيل

```bash
# للتطوير
python manage.py runserver

# للإنتاج
gunicorn bazarna.wsgi:application --workers 4
```

### الخطوة 5: التحقق

```bash
# اختبر أن كل شيء يعمل
python manage.py test
```

---

## إضافة دولة جديدة

### السيناريو

نريد إضافة السعودية كدولة جديدة مع إعداداتها الخاصة.

### الخطوات

#### 1. دخول Shell

```bash
python manage.py shell
```

#### 2. إنشاء الدولة

```python
from accounts.models import Country

saudi = Country.objects.create(
    name="المملكة العربية السعودية",
    code="SA",
    phone_code="+966",
    currency_name="ريال سعودي",
    currency_symbol="﷼",
    is_active=True,
    paymob_integration_id_card="SA_CARD_ID",
    paymob_integration_id_wallet="SA_WALLET_ID"
)
```

#### 3. إضافة المحافظات

```python
from store.models import Governorate

Governorate.objects.bulk_create([
    Governorate(country=saudi, name="الرياض"),
    Governorate(country=saudi, name="جدة"),
    Governorate(country=saudi, name="الخبر"),
    Governorate(country=saudi, name="الدمام"),
])
```

#### 4. إضافة الإعدادات

```python
from store.models import SiteSetting

settings = SiteSetting.objects.create(
    country=saudi,
    site_name="بازار السعودية",
    platform_fee_fixed=5.00,
    platform_fee_percentage=3.50,
    min_withdrawal_amount=100.00,
    min_wallet_balance=200.00,
    pending_balance_release_hours=48,
    referral_reward_amount=50.00,
    referral_grace_period_hours=24,
    active_payment_gateway='FAWATERK'
)
```

#### 5. إضافة مدير الدولة (اختياري)

```python
from accounts.models import User

admin = User.objects.create_user(
    username='saudi_admin',
    email='admin@saudi.bazarna.com',
    password='SecurePassword123',
    role='COUNTRY_ADMIN',
    country=saudi
)
```

#### 6. الخروج

```python
exit()
```

---

## الميزات الجديدة

### 1. الفلترة الذكية

#### استخدام صحيح:

```python
from supervisor.views import get_country_kwargs

# في View
orders = Order.objects.filter(
    **get_country_kwargs(request.user, 'customer__')
)
```

#### الفوائد:

- ✅ المشرف يرى بيانات دولته فقط
- ✅ المالك يرى كل البيانات
- ✅ كود موحد بدل التكرار

---

### 2. الخدمات (Services)

#### استخدام صحيح:

```python
from store.services import OrderService

# حساب الشحن
shipping, is_free = OrderService.calculate_merchant_shipping(
    merchant=merchant,
    governorate=gov,
    items=order_items,
    is_first_order=True
)

# حساب الرسوم
fees = OrderService.calculate_gateway_fees(
    amount=total,
    country=country
)
```

#### الفوائد:

- ✅ عمليات معقدة في مكان واحد
- ✅ سهل الاختبار والصيانة
- ✅ إعادة استخدام الكود

---

### 3. الإعدادات المحلية

#### استخدام صحيح:

```python
from store.models import SiteSetting

# الحصول على إعدادات الدولة
settings = SiteSetting.get_settings(country)

# الوصول للبيانات
fee = settings.platform_fee_fixed
percentage = settings.platform_fee_percentage
```

#### الفوائد:

- ✅ إعدادات مختلفة لكل دولة
- ✅ الحصول على الإعدادات تلقائياً
- ✅ إدارة مركزية

---

## أفضل الممارسات

### 1. استخدام Transactions

```python
from django.db import transaction

@transaction.atomic
def process_order(order):
    # كل العمليات معاً أو لا شيء
    order.status = 'PROCESSING'
    order.save()

    merchant.wallet.balance += amount
    merchant.wallet.save()
```

### 2. استخدام Signals

```python
from django.db.models.signals import post_save

@receiver(post_save, sender=Order)
def notify_on_order(sender, instance, created, **kwargs):
    if created:
        send_notification(
            instance.customer,
            "تم استلام طلبك",
            f"رقم الطلب: {instance.order_id}"
        )
```

### 3. التحقق من الصلاحيات

```python
from supervisor.views import is_supervisor

@login_required
def admin_dashboard(request):
    if not is_supervisor(request.user):
        return redirect('home')
    # الكود
```

---

## استكشاف الأخطاء

### المشكلة: بيانات مختلطة بين الدول

**الحل:**

```python
# ❌ خطأ
products = Product.objects.all()

# ✅ صحيح
products = Product.objects.filter(
    **get_country_kwargs(request.user)
)
```

### المشكلة: استعلامات بطيئة

**الحل:**

```python
# ✅ استخدم select_related و prefetch_related
products = Product.objects.select_related(
    'merchant',
    'category'
).prefetch_related(
    'images',
    'variations'
).filter(country=country)
```

### المشكلة: أخطاء في الدفع

**الحل:**

```python
# تحقق من gateway المختار
settings = SiteSetting.get_settings(country)
if settings.active_payment_gateway == 'PAYMOB':
    # استخدم Paymob
else:
    # استخدم Fawaterk
```

---

## نصائح للتطوير

1. **اقرأ التوثيق قبل التطوير** 📖
2. **استخدم Transactions للعمليات الحساسة** 💾
3. **اختبر مع دول مختلفة** 🌍
4. **سجل التغييرات في CHANGELOG** 📝
5. **استخدم version control** 🔀

---

## الموارد

### الملفات المهمة

```
PROJECT_SUMMARY_AR.md        # الملخص الشامل
CHANGELOG_AR.md              # سجل التغييرات
README_AR.md                 # الدليل السريع
```

### الملفات البرمجية

```
accounts/models.py           # Country, User
store/models.py              # Product, Order, Wallet
store/services.py            # الخدمات
supervisor/views.py          # الفلترة الذكية
```

---

## الدعم

للمساعدة أو الإبلاغ عن مشاكل:

- 📧 البريد: support@bazarna.com
- 💬 GitHub Issues: [اضغط هنا](https://github.com/U-WWW/bazar/issues)
- 📞 الدعم الفني: +20 1234 567890

---

**آخر تحديث:** أبريل 21، 2026  
**الإصدار:** 2.0.0
