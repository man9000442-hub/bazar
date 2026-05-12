# 🏪 Bazarna - منصة التجارة الإلكترونية متعددة الدول

> **منصة تجارة إلكترونية احترافية متعددة الدول مع نظام إدارة متقدم وتكاملات دفع عالمية**

---

## 📋 جدول المحتويات

1. [نظرة عامة](#نظرة-عامة)
2. [البدء السريع](#البدء-السريع)
3. [البنية المعمارية](#البنية-المعمارية)
4. [الموديلات الرئيسية](#الموديلات-الرئيسية)
5. [نظام الأدوار والصلاحيات](#نظام-الأدوار-والصلاحيات)
6. [الميزات الرئيسية](#الميزات-الرئيسية)
7. [التكاملات](#التكاملات)
8. [قاعدة البيانات](#قاعدة-البيانات)
9. [API والواجهات](#api-والواجهات)
10. [قواعد الترميز](#قواعد-الترميز)
11. [استكشاف الأخطاء](#استكشاف-الأخطاء)
12. [المساهمة](#المساهمة)

---

## 🎯 نظرة عامة

### ما هو Bazarna؟

**Bazarna** هي منصة تجارة إلكترونية متطورة تم بناؤها بـ Django وتدعم:

- ✅ **عدة دول وعملات** - نظام متقدم للدول والعملات
- ✅ **نظام بائع/مشتري** - إدارة متقدمة للتجار والعملاء
- ✅ **محافظ رقمية** - نظام دفع وتحويل أموال آمن
- ✅ **نظام طلبات متقدم** - تتبع وإدارة طلبات كاملة
- ✅ **نظام توثيق KYC** - معايير أمان عالية
- ✅ **نظام إحالات** - برنامج عمولات احترافي

### المتطلبات الأساسية

```
Python 3.9+
Django 6.0.2
PostgreSQL 12+
Redis (اختياري)
```

### الملفات الرئيسية للمشروع

```
bazarna/                    # مجلد المشروع الرئيسي
├── settings.py           # إعدادات Django
├── urls.py               # الروابط الرئيسية
├── wsgi.py               # تكوين WSGI
└── asgi.py               # تكوين ASGI

store/                     # تطبيق المتجر الرئيسي
├── models.py             # نماذج البيانات
├── views.py              # المناظر (Views)
├── urls.py               # الروابط
├── forms.py              # النماذج
└── admin.py              # لوحة الإدارة

accounts/                  # تطبيق الحسابات
├── models.py             # نماذج المستخدمين
├── views.py              # مناظر المستخدمين
└── forms.py              # نماذج التسجيل

merchant_panel/            # لوحة التاجر
supervisor/                # لوحة المشرف
support/                   # نظام الدعم
templates/                 # ملفات HTML
static/                    # ملفات CSS/JS ثابتة
media/                     # الملفات المرفوعة
locale/                    # ملفات الترجمة
md/                        # ملفات التوثيق
```

---

## 🚀 البدء السريع

### 1. تثبيت المتطلبات

```bash
# نسخ المستودع
git clone https://github.com/U-WWW/bazar.git
cd bazarna

# إنشاء بيئة افتراضية
python -m venv venv

# تفعيل البيئة
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# تثبيت المكتبات
pip install -r requirements.txt
```

### 2. إعداد المتغيرات البيئية

```bash
# نسخ ملف المثال
cp .env.example .env

# قم بتحرير .env وأضف:
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:password@localhost:5432/bazarna
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 3. إعداد قاعدة البيانات

```bash
# تطبيق الهجرات
python manage.py migrate

# إنشاء حساب إداري
python manage.py createsuperuser

# تحميل البيانات الأولية (اختياري)
python manage.py loaddata fixtures/countries.json
```

### 4. تشغيل الخادم

```bash
# تشغيل الخادم التطويري
python manage.py runserver

# سيكون المشروع متاحاً على:
# http://localhost:8000
# لوحة الإدارة: http://localhost:8000/admin
```

---

## 🏗️ البنية المعمارية

### النمط المعماري

يتبع المشروع نمط **MTV (Model-Template-View)**:

```
┌─────────────────┐
│   المستخدم      │
└────────┬────────┘
         │
    ┌────▼────┐
    │ Frontend │  (HTML/CSS/JavaScript)
    └────┬────┘
         │
    ┌────▼────┐
    │ Templates│  (render المحتوى)
    └────┬────┘
         │
    ┌────▼────┐
    │  Views   │  (معالجة الطلبات)
    └────┬────┘
         │
    ┌────▼────┐
    │ Models   │  (تعريف البيانات)
    └────┬────┘
         │
    ┌────▼────┐
    │Database  │  (PostgreSQL)
    └──────────┘
```

### طبقات التطبيق

#### 1️⃣ طبقة العرض (Views)

**ملف:** `store/views.py`

```python
# مثال على View بسيط
@login_required
def customer_privacy_policy(request):
    """
    عرض سياسة الخصوصية للعميل

    المعاملات:
    - request: طلب HTTP

    الإرجاع:
    - HttpResponse يحتوي على صفحة سياسة الخصوصية
    """
    current_country = get_user_country(request)
    policies = TermsAndCondition.objects.filter(
        document_type=TermsAndCondition.DocType.PRIVACY,
        user_type=TermsAndCondition.UserType.CUSTOMER,
        is_active=True
    ).filter(
        Q(country=current_country) | Q(country__isnull=True)
    ).order_by('order')

    context = {'policies': policies}
    return render(request, 'store/privacy_policy.html', context)
```

#### 2️⃣ طبقة النماذج (Models)

**ملف:** `store/models.py`

تعريف بنية البيانات والعلاقات بينها.

#### 3️⃣ طبقة قوالب HTML (Templates)

**مجلد:** `templates/`

عرض البيانات للمستخدم.

---

## 📊 الموديلات الرئيسية

### 1. نموذج حساب المستخدم (User Account)

```python
# من accounts/models.py

class CustomUser(AbstractUser):
    """نموذج مستخدم مخصص مع ميزات إضافية"""

    ROLE_CHOICES = [
        ('customer', 'عميل'),
        ('merchant', 'تاجر'),
        ('support', 'موظف دعم'),
        ('supervisor', 'مشرف'),
        ('admin', 'مسؤول'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True)
    phone = models.CharField(max_length=20)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 2. نموذج بروفايل التاجر (Merchant Profile)

```python
# من store/models.py

class MerchantProfile(models.Model):
    """بروفايل التاجر مع نظام التوثيق KYC"""

    class RankChoices(models.TextChoices):
        NONE = 'NONE', 'غير موثق'
        SILVER = 'SILVER', 'توثيق فضي'
        BLUE = 'BLUE', 'توثيق أزرق'
        GOLD = 'GOLD', 'توثيق ذهبي'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='merchant_profile'
    )

    shop_image = models.ImageField(
        upload_to='shops/',
        verbose_name="صورة المحل/الشخصية"
    )

    minimum_balance_required = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00
    )

    is_approved = models.BooleanField(
        default=False,
        verbose_name="تمت الموافقة من المشرف"
    )

    verification_rank = models.CharField(
        max_length=10,
        choices=RankChoices.choices,
        default=RankChoices.NONE
    )

    def __str__(self):
        return f"متجر: {self.user.username}"
```

### 3. نموذج المنتج (Product)

```python
class Product(models.Model):
    """نموذج المنتج الرئيسي"""

    merchant = models.ForeignKey(
        MerchantProfile,
        on_delete=models.CASCADE,
        related_name='products'
    )

    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True
    )

    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
```

### 4. نموذج الطلب (Order)

```python
class Order(models.Model):
    """نموذج الطلب الرئيسي"""

    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('confirmed', 'مؤكد'),
        ('shipped', 'مُرسل'),
        ('delivered', 'مُسلم'),
        ('cancelled', 'ملغى'),
    ]

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    shipping_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"طلب #{self.id} - {self.customer.username}"
```

### 5. نموذج المحفظة (Wallet)

```python
class Wallet(models.Model):
    """محفظة المستخدم الرقمية"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )

    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )

    currency = models.CharField(max_length=3, default='EGP')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"محفظة {self.user.username} - {self.balance} {self.currency}"
```

### 6. نموذج حركات المحفظة (Wallet Transaction)

```python
class WalletTransaction(models.Model):
    """تسجيل عمليات المحفظة"""

    TRANSACTION_TYPES = [
        ('deposit', 'إيداع'),
        ('withdrawal', 'سحب'),
        ('transfer', 'تحويل'),
        ('refund', 'استرجاع'),
    ]

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )

    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()

    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} - {self.amount} EGP"
```

### 7. نموذج الفئات (Category)

```python
class Category(models.Model):
    """فئات المنتجات"""

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name
```

---

## 👥 نظام الأدوار والصلاحيات

### الأدوار الستة في النظام

#### 1️⃣ العميل (Customer)

**الصلاحيات:**

- ✅ تصفح المنتجات
- ✅ شراء المنتجات
- ✅ إدارة سلة التسوق
- ✅ تتبع الطلبات
- ✅ كتابة التقييمات والتعليقات
- ✅ إضافة للمفضلات
- ✅ الوصول للمحفظة الشخصية

**URL الرئيسية:** `/store/` , `/account/`

#### 2️⃣ التاجر (Merchant)

**الصلاحيات:**

- ✅ إنشاء وتعديل المنتجات
- ✅ إدارة المخزون
- ✅ عرض الطلبات الخاصة به
- ✅ إدارة الشحن والتسليم
- ✅ الوصول للمحفظة والأرباح
- ✅ إدارة بروفايل المتجر

**URL الرئيسية:** `/merchant_panel/`

#### 3️⃣ موظف الدعم (Support Staff)

**الصلاحيات:**

- ✅ الرد على استفسارات العملاء
- ✅ التعامل مع الشكاوى
- ✅ إنشاء تذاكر دعم
- ✅ عرض معلومات المستخدمين

**URL الرئيسية:** `/support/`

#### 4️⃣ المشرف (Supervisor/Moderator)

**الصلاحيات:**

- ✅ إدارة التجار والعملاء
- ✅ مراجعة توثيق KYC
- ✅ إدارة الفئات والمنتجات
- ✅ عرض تقارير شاملة
- ✅ التعامل مع الشكاوى الخطيرة

**URL الرئيسية:** `/supervisor/`

#### 5️⃣ مسؤول النظام (Admin)

**الصلاحيات:**

- ✅ الوصول الكامل لكل شيء
- ✅ إدارة المستخدمين والأدوار
- ✅ إدارة النظام والإعدادات
- ✅ عرض وتحليل البيانات
- ✅ إدارة البيانات الحساسة

**URL الرئيسية:** `/admin/`

---

## 💡 الميزات الرئيسية

### 1. نظام الدول والعملات

**الملف:** `store/models.py`

```python
# نموذج الدول
class Country(models.Model):
    """دعم عدة دول بعملات مختلفة"""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=2, unique=True)  # مثل EG, SA, AE
    currency = models.CharField(max_length=3)  # EGP, SAR, AED

    is_active = models.BooleanField(default=True)
```

**الاستخدام:**

```python
# الحصول على دولة المستخدم
current_country = get_user_country(request)

# فلترة المنتجات حسب الدولة
products = Product.objects.filter(country=current_country)
```

### 2. نظام المحافظ الرقمية

**الميزات:**

- 💰 إيداع وسحب أموال
- 💸 تحويل بين المحافظ
- 📊 تتبع كامل للحركات
- 🔒 أمان عالي للمعاملات

**المثال:**

```python
# إيداع أموال في المحفظة
wallet = request.user.wallet
wallet.balance += amount
wallet.save()

# تسجيل العملية
WalletTransaction.objects.create(
    wallet=wallet,
    type='deposit',
    amount=amount,
    balance_before=wallet.balance - amount,
    balance_after=wallet.balance,
    description=f'إيداع مبلغ {amount}'
)
```

### 3. نظام الطلبات المتقدم

**الميزات:**

- 📦 تتبع الطلبات في الوقت الفعلي
- 🚚 إدارة الشحن والتسليم
- 📋 قائمة بتفاصيل المنتجات في الطلب
- 💳 نظام الدفع المتقدم

### 4. نظام التوثيق KYC

**المستويات:**

- 🟡 **عادي (None)** - بدون توثيق
- 🟢 **فضي (Silver)** - توثيق أساسي
- 🔵 **أزرق (Blue)** - توثيق متقدم
- 🟣 **ذهبي (Gold)** - توثيق كامل

### 5. نظام التقييمات والتعليقات

```python
# إضافة تقييم للمنتج
@login_required
def submit_review(request, product_id):
    """إضافة تقييم للمنتج"""

    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')

        Review.objects.create(
            product=product,
            customer=request.user,
            rating=rating,
            comment=comment
        )
```

### 6. نظام الإحالات والعمولات

```python
# نموذج الإحالة
class Referral(models.Model):
    """نظام الإحالات والعمولات"""

    referrer = models.ForeignKey(User, on_delete=models.CASCADE)
    referred_user = models.ForeignKey(User, on_delete=models.CASCADE)

    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    total_commission = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 🔌 التكاملات

### 1. نظام الدفع (Paymob)

**الملف:** `store/integrations/paymob.py`

```python
# تكامل Paymob للدفع
class PaymobIntegration:
    """تكامل نظام دفع Paymob"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://accept.paymob.com/api"

    def create_payment_intent(self, order, amount):
        """إنشاء نية دفع"""
        # كود التكامل
        pass

    def verify_payment(self, transaction_id):
        """التحقق من الدفع"""
        # كود التكامل
        pass
```

### 2. نظام البريد الإلكتروني

```python
# إرسال بريد تأكيد الطلب
from django.core.mail import send_mail

def send_order_confirmation(order):
    """إرسال تأكيد الطلب للعميل"""

    subject = f'تأكيد طلبك #{order.id}'
    message = f'شكراً على طلبك. الرقم: {order.id}'

    send_mail(
        subject,
        message,
        'noreply@bazarna.com',
        [order.customer.email],
        fail_silently=False,
    )
```

### 3. نظام الترجمة (i18n)

**الملف:** `locale/`

```python
# استخدام الترجمة في التطبيق
from django.utils.translation import gettext_lazy as _

title = _('مرحباً بك في Bazarna')
```

---

## 📁 قاعدة البيانات

### الجداول الرئيسية

| الجدول                  | الوصف          | العلاقات                |
| ----------------------- | -------------- | ----------------------- |
| `auth_user`             | المستخدمين     | -                       |
| `store_product`         | المنتجات       | user → merchant_profile |
| `store_order`           | الطلبات        | user → customer         |
| `store_wallet`          | المحافظ        | user → OneToOne         |
| `store_category`        | الفئات         | -                       |
| `store_merchantprofile` | بروفايل التاجر | user → OneToOne         |

### الهجرات (Migrations)

```bash
# إنشاء هجرة جديدة
python manage.py makemigrations

# تطبيق الهجرات
python manage.py migrate

# الاطلاع على حالة الهجرات
python manage.py showmigrations
```

---

## 🔌 API والواجهات

### نقاط النهاية الرئيسية (Endpoints)

#### متاجر الملابس

```
GET    /api/products/           - قائمة المنتجات
GET    /api/products/<id>/      - تفاصيل منتج
POST   /api/products/           - إنشاء منتج (للتاجر)
PUT    /api/products/<id>/      - تحديث منتج
DELETE /api/products/<id>/      - حذف منتج
```

#### الطلبات

```
GET    /api/orders/             - قائمة الطلبات
GET    /api/orders/<id>/        - تفاصيل الطلب
POST   /api/orders/             - إنشاء طلب جديد
PUT    /api/orders/<id>/        - تحديث حالة الطلب
```

#### المحافظ

```
GET    /api/wallet/             - الرصيد والحركات
POST   /api/wallet/deposit/     - إيداع أموال
POST   /api/wallet/withdraw/    - سحب أموال
POST   /api/wallet/transfer/    - تحويل لمحفظة أخرى
```

### مثال على استخدام API

```bash
# الحصول على قائمة المنتجات
curl -X GET http://localhost:8000/api/products/ \
  -H "Authorization: Token YOUR_TOKEN"

# إنشاء منتج جديد
curl -X POST http://localhost:8000/api/products/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "منتج جديد",
    "price": 100.00,
    "description": "وصف المنتج"
  }'
```

---

## 📝 قواعد الترميز

### 1. تسمية المتغيرات

```python
# ✅ صحيح
user_name = "Ahmed"
product_price = 100.50
is_active = True

# ❌ خطأ
u_name = "Ahmed"
pp = 100.50
active = True
```

### 2. تسمية الدوال

```python
# ✅ صحيح
def get_user_country(request):
    pass

def create_wallet_transaction(wallet, amount, type):
    pass

# ❌ خطأ
def get_country(request):
    pass

def create_trans(w, a, t):
    pass
```

### 3. التعليقات والتوثيق

```python
def process_order(order_id):
    """
    معالجة الطلب وتحديث حالته

    المعاملات:
    - order_id (int): معرف الطلب

    الإرجاع:
    - bool: True إذا نجحت العملية، False غير ذلك

    الاستثناءات:
    - Order.DoesNotExist: إذا لم يوجد الطلب
    """
    order = Order.objects.get(id=order_id)
    # ... الكود ...
    return True
```

### 4. استخدام F() و Q()

```python
# استخدام F() للعمليات الحسابية
from django.db.models import F, Q

# ✅ صحيح
Product.objects.filter(stock__gt=0).update(
    stock=F('stock') - 1
)

# استخدام Q() للشروط المعقدة
# ✅ صحيح
users = User.objects.filter(
    Q(role='merchant') | Q(role='admin')
).filter(
    is_active=True
)
```

### 5. إدارة الأخطاء

```python
# ✅ صحيح
try:
    order = Order.objects.get(id=order_id)
except Order.DoesNotExist:
    return Response(
        {'error': 'الطلب غير موجود'},
        status=status.HTTP_404_NOT_FOUND
    )

# ❌ تجنب
try:
    pass
except:
    pass
```

### 6. استخدام Decorators

```python
# ✅ صحيح
@login_required
@permission_required('store.change_product')
def edit_product(request, product_id):
    # فقط المستخدمين المسجلين
    # فقط الذين لديهم صلاحية تعديل المنتج
    pass
```

---

## 🔧 استكشاف الأخطاء

### الأخطاء الشائعة وحلولها

#### ❌ خطأ: `ImportError`

```
المشكلة: ModuleNotFoundError: No module named 'store'
```

**الحل:**

```bash
# تأكد من إضافة التطبيق في INSTALLED_APPS
# في settings.py:

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'store',  # ✅ أضفه هنا
    'accounts',
]
```

#### ❌ خطأ: `OperationalError`

```
المشكلة: operator "=" does not exist: uuid = integer
```

**الحل:**

```bash
# قم بحذف الهجرات القديمة والبيانات
python manage.py migrate store zero  # إرجاع الهجرات

# ثم أعد الهجرات
python manage.py migrate
```

#### ❌ خطأ: `AttributeError`

```
المشكلة: 'QuerySet' object has no attribute 'get'
```

**الحل:**

```python
# ❌ خطأ
product = Product.objects.filter(id=1).get()

# ✅ صحيح
product = Product.objects.get(id=1)
```

#### ❌ خطأ: `IntegrityError`

```
المشكلة: duplicate key value violates unique constraint
```

**الحل:**

```bash
# تحقق من البيانات المكررة
python manage.py shell
>>> from store.models import Product
>>> Product.objects.values('name').annotate(count=Count('id')).filter(count__gt=1)
```

#### ❌ خطأ: `ValidationError`

```
المشكلة: This field may not be blank
```

**الحل:**

```python
# ✅ التحقق قبل الحفظ
if not product.name:
    raise ValidationError("اسم المنتج مطلوب")
```

---

## 📚 المساهمة

### خطوات المساهمة

#### 1. نسخ المستودع

```bash
git clone https://github.com/U-WWW/bazar.git
cd bazarna
```

#### 2. إنشاء فرع جديد

```bash
# استخدم أسماء واضحة للفروع
git checkout -b feature/اسم-الميزة
# أو
git checkout -b bugfix/اسم-الخطأ
```

#### 3. إجراء التغييرات

```bash
# عدّل الملفات المطلوبة
# اختبر التغييرات محلياً
python manage.py test

# تأكد من قواعس الترميز
flake8 .
```

#### 4. Commit والـ Push

```bash
# Commit التغييرات مع رسالة واضحة
git add .
git commit -m "إضافة ميزة: وصف واضح"

# Push الفرع
git push origin feature/اسم-الميزة
```

#### 5. فتح Pull Request

- اذهب للمستودع على GitHub
- انقر على "New Pull Request"
- اختر الفرع الخاص بك
- أضف وصفاً مفصلاً
- انتظر المراجعة

### معايير الكود

- ✅ كل الاختبارات يجب أن تمر
- ✅ لا توجد أخطاء في الترميز (flake8)
- ✅ التعليقات واضحة بالعربية
- ✅ الوثائق محدثة

---

## 📞 الدعم والمساعدة

### الاتصال والدعم

| القناة           | التفاصيل                                          |
| ---------------- | ------------------------------------------------- |
| 📧 البريد        | support@bazarna.com                               |
| 💬 GitHub Issues | [اضغط هنا](https://github.com/U-WWW/bazar/issues) |
| 📱 WhatsApp      | +20 1234 567890                                   |
| 🌐 الموقع        | https://elbazaare.com                             |

### الأسئلة الشائعة

**س: كيف أضيف دولة جديدة؟**

جـ: اتبع `MIGRATION_GUIDE_AR.md` في مجلد `md/`

**س: كيف أقوم بالترقية من الإصدار 1.0 إلى 2.0؟**

جـ: اتبع خطوات الترقية في `MIGRATION_GUIDE_AR.md`

**س: كيف أعدّل صيغة البريد الإلكتروني؟**

جـ: عدّل القوالب في `templates/email/`

---

## 📋 الملخص

| الجانب             | التفاصيل                   |
| ------------------ | -------------------------- |
| **اللغة**          | Python 3.9+                |
| **Framework**      | Django 6.0.2               |
| **قاعدة البيانات** | PostgreSQL 12+             |
| **الإصدار الحالي** | 2.0.0                      |
| **الحالة**         | ✅ منتج (Production Ready) |
| **الترخيص**        | MIT License                |

---

**آخر تحديث:** أبريل 21، 2026  
**الحالة:** ✅ كامل وجاهز للإنتاج  
**الدعم:** 24/7

---

## 📄 الملفات الإضافية

- [README_AR.md](./md/README_AR.md) - دليل سريع بالعربية
- [PROJECT_SUMMARY_AR.md](./md/PROJECT_SUMMARY_AR.md) - ملخص شامل
- [CHANGELOG_AR.md](./md/CHANGELOG_AR.md) - سجل التغييرات
- [MIGRATION_GUIDE_AR.md](./md/MIGRATION_GUIDE_AR.md) - دليل الترقية
- [DOCUMENTATION_INDEX_AR.md](./md/DOCUMENTATION_INDEX_AR.md) - فهرس الوثائق
