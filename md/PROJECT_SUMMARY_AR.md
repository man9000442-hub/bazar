# 📘 توثيق مشروع Bazarna الشامل# 🌍 مشروع Bazarna - ملخص شامل محدّث (2026)

**الإصدار:** 2.0.0 ## 📌 الملخص التنفيذي

**التاريخ:** أبريل 21، 2026

**الحالة:** ✅ منتج وفي الإنتاج **Bazarna** هي منصة تجارة إلكترونية **B2C متعددة الدول** (Multi-Country) مكتوبة بـ **Django 6.0** و **PostgreSQL/SQLite** لتشغيل أسواق متعددة في دول مختلفة.

---**موقع الإنتاج:** `elbazaare.com` و `www.elbazaare.com`

## 📑 الفهرس---

1. [النظرة العامة](#النظرة-العامة)## 🔥 أهم التحديثات (الإصدار الجديد)

2. [البنية المعمارية](#البنية-المعمارية)

3. [نظام الأدوار والصلاحيات](#نظام-الأدوار-والصلاحيات)### 1. **✨ نظام متعدد الدول (Multi-Country System)**

4. [الميزات الرئيسية](#الميزات-الرئيسية)

5. [نظام الدول](#نظام-الدول-multi-country)تم إضافة دعم **كامل** لإدارة عدة دول بشكل منفصل:

6. [الموديلات الأساسية](#الموديلات-الأساسية)

7. [نظام المعاملات المالية](#نظام-المعاملات-المالية)#### موديل `Country` الجديد:

8. [الدعم الفني](#الدعم-الفني)

````python

---class Country(models.Model):

    name                      # اسم الدولة (مثل: مصر، السعودية)

## النظرة العامة    code                      # كود الدولة (EG, SA)

    phone_code                # +20, +966

**Bazarna** منصة تجارة إلكترونية متعددة الدول مبنية بـ **Django 6.0** توفر:    currency_name             # جنيه مصري، ريال سعودي

    currency_symbol           # ج.م, ﷼

- ✅ إدارة متعددة الدول مع معايير محلية    is_active                 # تفعيل/تعطيل الدولة

- ✅ نظام أدوار متقدم (6 أدوار)

- ✅ معالجة دفع متعددة (Paymob, Fawaterk)    # 🔥 إعدادات بوابات الدفع المنفصلة لكل دولة

- ✅ لوحات تحكم متخصصة (تاجر، إدارة، دعم)    paymob_integration_id_card    # ID شحن البطاقات

- ✅ نظام محافظ رقمية وإدارة رصيد    paymob_integration_id_wallet  # ID شحن المحافظ

- ✅ دعم فني متطور مع تتبع تذاكر```



**الموقع:** https://elbazaare.com#### الربط بجميع الكيانات الرئيسية:



---- `User.country` - ربط المستخدم بدولته

- `Product.country` - ربط المنتج بدولة التاجر

## البنية المعمارية- `Order.country` - ربط الطلب بدولة العميل

- `Governorate.country` - المحافظات مرتبطة بالدولة

```- `SiteSetting.country` - إعدادات منفصلة لكل دولة

┌─────────────────────────────────────────┐- `Banner.country`, `PromoPopup.country`, `TermsAndCondition.country` - كل محتوى يخص دولة معينة

│         Frontend (Templates + Static)   │

├─────────────────────────────────────────┤### 2. **👤 نظام الأدوار والصلاحيات المحسّن**

│  Django Views | REST API | WebSockets   │

├─────────────────────────────────────────┤#### الأدوار الجديدة:

│  Business Logic | Services | Signals    │

├─────────────────────────────────────────┤```python

│  ORM Models | Validators | Managers     │class User.Role:

├─────────────────────────────────────────┤    CUSTOMER       # عميل (المشتري)

│  PostgreSQL Database | Cache (Redis)    │    MERCHANT       # تاجر (البائع)

└─────────────────────────────────────────┘    OWNER          # مالك النظام (سوبر يوزر) - لا دولة محددة

```    COUNTRY_ADMIN  # 🔥 مدير الدولة - يدير دولة معينة فقط

    ADMIN_LVL2     # مشرف درجة 2 - مراجعة طلبات التجار الجدد

### المجلدات الرئيسية    ADMIN_LVL3     # مشرف درجة 3 - إدارة الدعم والشكاوى

````

| المجلد | الوصف |

| --------------- | ------------------------------ |#### الأدوار المخصصة (`CustomRole`):

| `accounts/` | 👥 المستخدمون والمصادقة |

| `store/` | 🛍️ المنتجات والطلبات |- ربط الأدوار بدول معينة

| `merchant_panel/` | 🏪 لوحة التاجر |- صلاحيات قابلة للتخصيص

| `supervisor/` | 👨‍💼 لوحة الإدارة |- فلترة ذكية في الـ Views

| `support/` | 🆘 الدعم الفني |

| `templates/` | 📄 القوالب |#### فلترة الدول:

| `static/` | 🎨 CSS و JavaScript |

```````python

---def get_country_kwargs(user, prefix=''):

    """

## نظام الأدوار والصلاحيات    إذا كان المشرف OWNER → لا فلترة (يرى كل شيء)

    إذا كان COUNTRY_ADMIN → يرى دولته فقط

### الأدوار الستة    إذا كان ADMIN_LVL2/3 → يرى دولته فقط

    """

```python    if user.is_superuser or user.role == 'OWNER':

1. CUSTOMER        # العميل - يشتري ويقيّم        return {}

2. MERCHANT        # التاجر - يبيع ويدير المحفظة    return {f"{prefix}country": user.country}

3. COUNTRY_ADMIN   # 🔥 مدير الدولة - إدارة محلية```

4. ADMIN_LVL2      # مشرف - موافقة على التجار

5. ADMIN_LVL3      # مشرف - معالجة الشكاوى### 3. **⚙️ إعدادات الموقع متعددة الدول (`SiteSetting`)**

6. OWNER           # المالك - وصول كامل

``````python

class SiteSetting(models.Model):

### نموذج الصلاحيات    country                         # ربط بدولة معينة (OneToOne)

    site_name                       # اسم الفرع (مثل: "بازار مصر")

```````

┌─────────────────────────────────┐ # 💰 إعدادات العمولة

│ OWNER (كل الدول، كل الصلاحيات) │ platform_fee_fixed # ثابتة (3 ج.م)

└─────────────────────────────────┘ platform_fee_percentage # نسبة (2.75%)

           │

    ┌──────┴──────┐    # 💳 إعدادات السحب والمحافظ

    │             │    min_withdrawal_amount           # حد أدنى للسحب

COUNTRY_ADMIN ADMIN_LVL2/3 min_wallet_balance # مبلغ محجوز في المحفظة

(دولة واحدة) (دول محددة) min_active_balance # الحد الأدنى لتفعيل المنتجات

    │             │    pending_balance_release_hours   # مدة تعليق الرصيد

    ├─ مراقبة     ├─ موافقة تجار

    ├─ إدارة      ├─ عروض    # 🎁 إعدادات الدعوات (Referral)

    └─ تقارير     └─ شكاوى    referral_reward_amount          # قيمة المكافأة

````referral_reward_limit_orders # عدد الطلبات المؤهلة

    referral_grace_period_hours     # مهلة إدخال الكود

---    referral_discount_limit_pct     # أقصى نسبة خصم



## الميزات الرئيسية    # 🎨 إعدادات البانر والإعلانات

    banner_image

### 1. نظام متعدد الدول 🌍

    # 💳 بوابة الدفع الفعالة لكل دولة

- دول منفصلة مع عملات وقوانين مختلفة    active_payment_gateway          # PAYMOB أو FAWATERK

- إعدادات خاصة لكل دولة

- بوابات دفع متعددة    @classmethod

- فلترة ذكية للبيانات    def get_settings(cls, country):

        """الحصول على الإعدادات مع الضمان إنها موجودة دايماً"""

### 2. إدارة المنتجات 🛍️        obj, created = cls.objects.get_or_create(country=country)

        return obj

- مقاسات وألوان متعددة```

- صور إضافية

- عروض وخصومات### 4. **🏪 نظام المحافظات المحسّن**

- تقييمات وتعليقات

```python

### 3. نظام الطلبات 📦class Governorate(models.Model):

    country                 # الدولة (ForeignKey)

- متابعة كاملة للحالة    name                    # اسم المحافظة

- حساب الأسعار التلقائي

- معالجة الشحن    class Meta:

- نظام المرتجعات        unique_together = ('country', 'name')

````

### 4. المحافظ الرقمية 💰

- كل دولة لها محافظاتها الخاصة

- رصيد التاجر- منع تكرار أسماء المحافظات في نفس الدولة

- معاملات تفصيلية- الربط التلقائي عند إنشاء طلب

- سحب أرباح

- شحن رصيد### 5. **🔐 نظام الإشعارات المحسّن**

### 5. نظام الدعوات 🎁#### `NotificationLog` الجديد:

- كود فريد لكل مستخدم```python

- مكافآت تلقائيةclass NotificationLog(models.Model):

- خصومات للعملاء user # المستخدم

- تتبع الإحصائيات title # عنوان الإشعار

  status # حالة الإرسال

### 6. الدعم الفني 🆘 details # تفاصيل أو رسالة إيرور

    created_at              # وقت الإرسال

- تذاكر دعم منظمة```

- تصنيف بالأولوية

- تعيين للمشرفين

- سجل الردود### 6. **📊 خدمات متقدمة (`services.py`)**

---```python

class OrderService:

## نظام الدول (Multi-Country) @staticmethod

    def calculate_merchant_shipping(merchant, governorate, items,

### موديل Country is_first_order=False,

                                    has_free_voucher=False):

````python """

Country:        حساب الشحن مع دعم:

  - name: str          # "مصر"        - أسعار شحن مختلفة لكل محافظة

  - code: str          # "EG"        - عروض الشحن المجاني

  - phone_code: str    # "+20"        - الشحن المجاني للطلب الأول

  - currency_name: str # "جنيه مصري"        - القسائم المجانية الشحن

  - currency_symbol: str # "ج.م"        """

  - is_active: bool

  - paymob_ids: (card, wallet)    @staticmethod

```    def calculate_gateway_fees(amount, country):

        """

### الربط في جميع الجداول        حساب رسوم البوابات بناءً على إعدادات الدولة

        - ثابتة + نسبة مئوية

```        - يختلف حسب الدولة

User.country        """

Product.country```

Order.country

Governorate.country### 7. **📁 هيكل المشروع المحدّث**

SiteSetting.country

Banner.country```

TermsAndCondition.countrybazarna/

PromoPopup.country├── accounts/

```│   ├── models.py          # ✨ Country, User (مع country field)

│   └── ...

### الفلترة الذكية├── store/

│   ├── models.py          # ✨ تحديثات النماذج لدعم الدول

```python│   ├── services.py        # 🆕 طبقة الخدمات

# كل مستخدم يرى بيانات دولته فقط│   └── ...

def get_country_kwargs(user):├── merchant_panel/

    if user.role == 'OWNER':│   ├── views.py           # ✨ فلترة ذكية حسب الدول

        return {}  # يرى الكل│   └── ...

    return {'country': user.country}├── supervisor/

```│   ├── views.py           # ✨ لوحة إدارة متعددة الدول

│   ├── urls.py            # 🆕 روابط إدارة الدول

---│   └── ...

└── ...

## الموديلات الأساسية```



### User (المستخدم)---



```python## 🏗️ البنية الكاملة للمشروع

- id

- username### الملفات الأساسية

- email

- password```

- role (CUSTOMER, MERCHANT, etc.)bazarna/

- country (FK)├── manage.py              # أداة إدارة Django

- is_banned: bool├── db.sqlite3             # قاعدة البيانات (تطوير)

- created_at├── requirements.txt       # المكتبات المطلوبة

```├── runtime.txt            # إصدار Python (3.10+)

├── Procfile               # تعريفات العمليات

### MerchantProfile (بيانات التاجر)├── firebase-key.json      # مفاتيح Firebase

└── .env                   # المتغيرات البيئية السرية

```python

- user (OneToOne)bazarna/                   # إعدادات المشروع

- shop_image├── settings.py            # ⚙️ جميع الإعدادات

- is_approved: bool├── urls.py                # الروابط الرئيسية

- is_verified: bool├── wsgi.py                # Gunicorn

- wallet (OneToOne) → محفظة└── asgi.py                # ASGI (اختياري)

- products (Many)

- orders (Many)accounts/                  # 👥 المستخدمون والمصادقة

```├── models.py              # User, Country, CustomRole, Address

├── backends.py            # مصادقة مخصصة (Email/Phone)

### Product (المنتج)├── adapters.py            # محولات Google

├── middleware.py          # فحص الحظر (BanMiddleware)

```python├── forms.py               # نماذج التسجيل

- merchant (FK)├── views.py               # صفحات الحساب

- country (FK)├── serializers.py         # REST serializers

- name├── api_views.py           # API endpoints

- description└── urls.py                # روابط الحسابات

- base_price

- category (FK)store/                     # 🛍️ المتجر والمنتجات

- image├── models.py              # Product, Order, Wallet, etc.

- images (Many)├── views.py               # صفحات المتجر الأساسية

- variations/sizes (Many)├── api_views.py           # REST API

- offer (OneToOne)├── serializers.py         # DRF serializers

- reviews (Many)├── services.py            # طبقة الخدمات

```├── paymob_utils.py        # تكامل Paymob

├── fawaterk__utils.py     # تكامل Fawaterk

### Order (الطلب)├── utils.py               # دوال مساعدة

├── signals.py             # Django signals

```python├── sitemaps.py            # خريطة الموقع (SEO)

- order_id: str (فريد)├── translation.py         # الترجمة

- customer (FK)├── context_processors.py  # معالجات السياق

- merchant (FK)├── management/            # أوامر مخصصة

- country (FK)└── urls.py

- status (CART, PENDING, SHIPPED, etc.)

- items (Many)merchant_panel/            # 🏪 لوحة التاجر

- total_price├── views.py               # إدارة المنتجات والطلبات

- final_total├── urls.py

- payment_method├── models.py

- created_at└── api_views.py

````

supervisor/ # 👨‍💼 لوحة الإدارة

### Wallet (المحفظة)├── views.py # إدارة النظام بالكامل

├── urls.py # روابط الإدارة

````python├── models.py              # (فارغ - تستخدم نماذج store)

- merchant (OneToOne)└── templatetags/          # وسوم مخصصة

- balance: decimal

- pending_balance: decimalsupport/                   # 🆘 نظام الدعم الفني

- updated_at├── models.py              # SupportTicket, TicketMessage

- transactions (Many)├── views.py

```├── urls.py

├── serializers.py

---├── api_views.py

└── context_processors.py

## نظام المعاملات المالية

templates/                 # 📄 القوالب HTML

### حساب السعر النهائي├── base.html              # قالب الأساس

├── store/                 # قوالب المتجر

```├── account/               # قوالب الحسابات

final_total = products_price + shipping - referral_discount + platform_fees├── merchant/              # قوالب لوحة التاجر

├── supervisor/            # قوالب لوحة الإدارة

platform_fees = fixed + (amount × percentage%)├── support/               # قوالب الدعم

```└── errors/



### أنواع معاملات المحفظةstatic/                    # 🎨 ملفات ثابتة

├── css/

| النوع        | الوصف                  |├── js/

| ------------ | ---------------------- |└── ...

| SALE         | ربح من بيع             |

| PENDING      | رصيد معلق              |media/                     # 📸 الصور المرفوعة

| WITHDRAWAL   | سحب أرباح              |├── banners/

| COMPENSATION | تعويض من الإدارة       |├── categories/

| REFUND       | خصم من مرتجع           |├── products/

├── product_gallery/

### طرق الدفع├── merchant_ids/

├── shops/

1. **COD** - الدفع عند الاستلام (افتراضي)└── promo_popups/

2. **ONLINE** - بطاقة بنكية (Paymob)

3. **WALLET** - محفظة إلكترونيةlocale/                    # 🌐 الترجمات

├── ar/

---└── en/



## الدعم الفنيstaticfiles/               # 📦 ملفات مضغوطة للإنتاج

````

### تذكرة الدعم

---

````python

- id## 👥 نظام المستخدمين والأدوار

- customer (FK)

- subject### 1️⃣ **العميل (CUSTOMER)**

- message

- status (OPEN, IN_PROGRESS, RESOLVED, CLOSED)- تصفح المنتجات

- priority (LOW, MEDIUM, HIGH)- إنشاء سلة تسوق

- assigned_to (FK)- وضع الطلبات

- messages (Many)- اختيار طرق الدفع (كاش، بطاقة، محفظة)

```- تقييم المنتجات بعد التسليم

- استخدام أكواد الدعوات

### الردود

### 2️⃣ **التاجر (MERCHANT)**

```python

- ticket (FK)- إنشاء متجر خاص

- sender (FK)- رفع المنتجات (مع مقاسات وألوان)

- message- إدارة المحفظة والرصيد

- is_support_reply: bool- شحن الرصيد عبر Paymob/Fawaterk

- created_at- سحب الأرباح

```- عرض عروضات

- تتبع الطلبات

---

### 3️⃣ **مدير الدولة (COUNTRY_ADMIN)** 🔥 جديد

## المتطلبات التقنية

- إدارة دولة واحدة فقط

### البرامج- رؤية جميع الطلبات والتجار في دولته

- إدارة إعدادات الدولة

- Python ≥ 3.10- موافقة على التجار الجدد

- PostgreSQL ≥ 12 (الإنتاج)- إدارة المحافظات

- Redis (اختياري، للـ Cache)

### 4️⃣ **مشرف درجة 2 (ADMIN_LVL2)**

### المكتبات الأساسية

- مراجعة طلبات التجار الجدد

```- موافقة/رفض التسجيل

Django==6.0.2- نشر عروض المنصة

djangorestframework==3.16.1

psycopg2-binary==2.9.11### 5️⃣ **مشرف درجة 3 (ADMIN_LVL3)**

requests==2.32.5

gunicorn==25.1.0- إدارة تذاكر الدعم الفني

```- معالجة الشكاوى والمرتجعات

- حل النزاعات

### الخدمات الخارجية

### 6️⃣ **مالك النظام (OWNER)**

- **Paymob** - معالجة الدفع

- **Fawaterk** - معالجة الدفع- صاحب المنصة الأساسي

- **Firebase** - إشعارات Push- وصول كامل لكل شيء

- **Google Cloud** - تخزين الملفات- إدارة الدول والعملات

- لا دولة محددة

---

---

## الملفات المهمة

## 💰 نظام المحفظة والمعاملات

````

bazarna/### المحفظة (`Wallet`)

├── settings.py # ⚙️ الإعدادات الرئيسية

├── urls.py # الروابط الرئيسية```

├── wsgi.py # GunicornMerchantProfile (1:1) ←→ Wallet

├── requirements.txt # المكتبات```

├── .env # المتغيرات السرية

└── manage.py # أداة Django**الرصيد يتأثر بـ:**

````

- ✅ بيع منتج → إضافة (السعر - العمولة)

---- ✅ شحن رصيد → إضافة

- ✅ سحب أرباح → خصم

## قواعد الكود الأساسية- ❌ مرتجع منتج → خصم

- ⏳ معاملات معلقة (مدة محددة)

### 1. استخدام الفلترة

### معاملات الرصيد (`WalletTransaction`)

```python

# ✅ صحيح| النوع            | الوصف                     |

products = Product.objects.filter(**get_country_kwargs(user))| ---------------- | ------------------------- |

| **SALE**         | ربح من بيع منتج           |

# ❌ خطأ| **PENDING**      | رصيد معلق (في فترة الحجز) |

products = Product.objects.all()| **COMPENSATION** | شحن أو تعويض من الإدارة   |

```| **WITHDRAWAL**   | سحب أرباح                 |

| **REFUND**       | خصم من مرتجع منتج         |

### 2. استخدام Services

### معاملات الشحن (`WalletDepositTransaction`)

```python

# ✅ صحيح- تسجيل عمليات شحن الرصيد

from store.services import OrderService- ربط بـ Paymob/Fawaterk

shipping = OrderService.calculate_merchant_shipping(...)- تتبع رقم الفاتورة والمعاملة



# ❌ خطأ - الحسابات في الـ View---

````

## 📦 نظام الطلبات المتقدم

### 3. استخدام select_related

### حالات الطلب (Order Status)

````python

# ✅ صحيح```

Product.objects.select_related('merchant', 'category')CART

  ↓

# ❌ خطأ - N+1 queriesWAITING_PAYMENT (إذا دفع أونلاين)

Product.objects.all()  ↓

```PENDING (انتظار موافقة التاجر)

  ↓

---APPROVED (وافق التاجر)

  ↓

## الإحصائياتSHIPPED (تم الشحن)

  ↓

- **1000+** سطر وثائقDELIVERED (وصل العميل)

- **20+** جدول في قاعدة البيانات  ↓ (اختياري)

- **6** أدوار مختلفةRETURNED (مرتجع)

- **8+** نقاط تكامل خارجيةCANCELLED (ملغى)

- **100+** endpoints API```



---### حساب الأسعار



## الحالة الحالية```

final_total = total_products_price + shipping_cost + platform_fees - referral_discount

| الجانب         | الحالة  |

| -------------- | ------ |platform_fees = fixed_fee + (amount × percentage%)

| التطوير        | ✅ مكتمل |```

| الاختبار       | ✅ مكتمل |

| الإنتاج        | 🟢 نشط |**مثال:**

| الوثائق        | ✅ محدثة |

| الصيانة        | ✅ مستمرة |```

منتج: 100 ج.م × 1

---الشحن: 30 ج.م

رسوم: 3 ج.م + (130 × 2.75%) = 6.58 ج.م

## الروابط المفيدةالإجمالي: 100 + 30 + 6.58 = 136.58 ج.م

````

| الرابط | الوصف |

| ---------------------- | ----------------- |### عناصر الطلب (`OrderItem`)

| https://elbazaare.com | الموقع الرسمي |

| GitHub Issues | الأخطاء المعروفة |- المنتج والمقاس

| Documentation | التوثيق الكامل |- الكمية

- السعر وقت الشراء

---- العمولة المحسوبة

- خصم الدعوة

## آخر التحديثات

### طرق الدفع

**الإصدار 2.0.0 - أبريل 2026:**

- ✅ نظام متعدد الدول1. **COD** - الدفع عند الاستلام (افتراضي)

- ✅ أدوار محسّنة2. **ONLINE** - بطاقة بنكية عبر Paymob

- ✅ خدمات متقدمة3. **WALLET** - محفظة إلكترونية

- ✅ إشعارات محسّنة

---

---

## 🎁 نظام الدعوات (Referral System)

**للمزيد:** اقرأ الملفات الأخرى في المجلد

### كيف يعمل؟

```
المدعي (User A)
    ↓
    يعطي رابط/كود: "ABC12345"
    ↓
المدعو (User B) يسجل
    ↓
    يشتري X طلبات
    ↓
✅ User A → يحصل على 50 ج.م
✅ User B → يحصل على خصم على المنتجات
```

### الحقول في User

- `referral_code`: كود فريد (8 حروف عشوائية)
- `invited_by`: من دعاه (ForeignKey self)
- `referral_balance`: رصيد المكافآت

### إعدادات الدعوات (في SiteSetting)

```python
referral_reward_amount = 50.00              # مكافأة المدعي
referral_reward_limit_orders = 1            # على أول X طلبات
referral_grace_period_hours = 24            # مهلة إدخال الكود
referral_discount_limit_pct = 10            # أقصى خصم على المنتج
```

### تطبيق الخصم

- ينطبق تلقائياً عند استخدام الكود
- مخزن في `OrderItem.referral_discount`
- لا يتجاوز 10% من سعر المنتج

---

## 💳 نظام الدفع (Paymob / Fawaterk)

### دعم بوابات متعددة

```python
class SiteSetting.PaymentGateway:
    PAYMOB = 'PAYMOB'           # Paymob (Egypt)
    FAWATERK = 'FAWATERK'       # Fawaterk (Multi-country)
```

### تدفق الدفع (Paymob)

```
1. العميل → يختار طريقة الدفع (بطاقة/محفظة)
2. Backend → get_token() من Paymob API
3. Backend → create_order() نموذج طلب دفع
4. Backend → get_payment_key() لفتح الـ Iframe
5. Frontend → Paymob Iframe/Redirect
6. العميل → يدخل بيانات الدفع
7. Paymob → Webhook Callback
8. Backend → معالجة الـ Callback وتحديث الطلب
```

### ملفات الدفع

#### `paymob_utils.py`

```python
class PaymobManager:
    def get_token()              # توكن المصادقة
    def create_order()           # إنشاء طلب دفع
    def get_payment_key()        # مفتاح دخول الـ Iframe
    def pay_with_wallet()        # دفع محفظة إلكترونية
```

#### `fawaterk__utils.py`

- تكامل Fawaterk للدول المتعددة

### Callbacks

- `/payment_callback/` - للعملاء (الطلبات)
- `/merchant/paymob-callback/` - للتجار (شحن الرصيد)

---

## 🛍️ نظام المنتجات المحسّن

### هيكل المنتج

```
Product
├── name, description, base_price
├── country (ForeignKey)         # 🔥 جديد: ربط بالدولة
├── category (ForeignKey)
├── merchant (ForeignKey → MerchantProfile)
├── image (الصورة الرئيسية)
├── ProductImage (صور إضافية - Many)
├── ProductSize (مقاسات وألوان - Many)
├── Offer (عروض - OneToOne)
├── ProductReview (تقييمات - Many)
└── active_offer
```

### المقاسات والألوان (`ProductSize`)

```python
class ProductSize:
    product         # المنتج
    size_label      # S, M, L, XL
    color_label     # أحمر، أزرق، أخضر
    stock_quantity  # الكمية المتاحة

    Meta:
        قيد فريد حسب: product + size + color
```

### العروض (`Offer`)

```python
class Offer:
    product                 # OneToOne
    discount_percentage     # نسبة الخصم
    start_date              # متى ينتهي؟
    end_date
    is_active               # مفعل؟
    is_platform_offer       # من المنصة (هناك تعويض) أم التاجر؟
    free_shipping           # شحن مجاني؟
    free_shipping_threshold # عند شراء X قطعة
```

### التقييمات (`ProductReview`)

- تقييم من 1 إلى 5 نجوم
- تعليق اختياري
- مراقبة الفهرس (unique: product + user)

---

## 🎨 إعدادات الموقع والمحتوى

### `SiteSetting` الشاملة

لكل دولة:

- 💰 رسوم ومحفظة
- 🎁 إعدادات الدعوات
- 🎨 محتوى البانر
- 💳 بوابة الدفع الفعالة

### `Banner` (الإعلانات)

- ربط بدولة معينة
- صورة ورابط توجيه
- تاريخ انتهاء
- حالة نشط/غير نشط

### `TermsAndCondition` (الشروط)

```python
class TermsAndCondition:
    country                 # الدولة
    title                   # عنوان البند
    content                 # النص
    document_type           # TERMS, PRIVACY, SHIPPING_RETURN
    user_type               # CUSTOMER أو MERCHANT
    order                   # ترتيب العرض
```

### `PromoPopup` (الإعلانات المنبثقة)

```python
class PromoPopup:
    country                 # الدولة
    image                   # صورة الإعلان
    offer                   # ربط بعرض نشط
    custom_link             # أو رابط مخصص
    start_time, end_time    # فترة الظهور

    # 🔥 تحقق من عدم تعارض الإعلانات
    validate_no_overlap()
```

### `AboutUs` (صفحة من نحن)

```python
class AboutUs:
    country                 # منفصل لكل دولة
    content
    updated_at
```

### `PersonalVoucher` (قسائم مخصصة)

```python
class PersonalVoucher:
    customer                # العميل
    code                    # كود الخصم
    discount_percentage     # النسبة
    max_discount_amount     # الحد الأقصى
    remaining_items         # كم منتج متبقي
    free_shipping
    expires_at
```

---

## 📋 نظام المرتجعات والشكاوى

### المرتجعات (`ReturnRequest`)

```python
class ReturnRequest:
    Status:
        PENDING     → قيد المراجعة
        APPROVED    → مقبول (بانتظار الاستلام)
        REFUNDED    → تم الاستلام والاسترجاع
        REJECTED    → مرفوض

    order                       # الطلب الأصلي
    customer
    reason                      # سبب الإرجاع
    customer_wallet_number      # رقم محفظة للاسترداد
    refund_amount              # المبلغ المستحق
```

### شكاوى الاستلام (`DeliveryComplaint`)

```python
class DeliveryComplaint:
    order
    customer
    complaint_text          # نص الشكوى
    is_resolved             # تم حلها؟
    admin_notes             # تعليقات الإدارة
    whatsapp_number         # للتواصل
```

---

## 🛡️ نظام الأمان والمصادقة

### طرق المصادقة

1. **Email + Password** - التقليدية
2. **Phone + Password** - عبر رقم الهاتف
3. **Google Sign-up** - عبر django-allauth
4. **المصادقة المخصصة** - Backend يقبل Email/Phone/Username

### Backend المخصص

```python
class EmailPhoneUsernameBackend:
    """
    يتقبل:
    - البريد الإلكتروني
    - رقم الهاتف
    - اسم المستخدم
    """
```

### نظام الحظر (`BanMiddleware`)

```python
class BanMiddleware:
    # فحص is_banned على كل طلب
    # إذا محظور → إعادة لصفحة banned.html
```

### الأمان

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# مدة الجلسة
SESSION_COOKIE_AGE = 1209600  # 14 يوم
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
```

---

## 🔍 البحث والفلترة

### البحث العام

- بحث حسب اسم المنتج
- بحث حسب الوصف
- دعم الأحرف العربية

### التصفية المتقدمة

- حسب القسم/الفئة
- حسب السعر
- حسب التقييم
- حسب حالة التاجر (موثق/غير موثق)
- حسب المحافظة (للشحن)

### شروط ظهور المنتج

```python
product.is_active == True              # نشط
product.is_approved == True            # موافق
product.country == current_country     # من الدولة الحالية
product.merchant.is_approved == True   # التاجر موافق عليه
merchant.wallet.balance >= min_balance # رصيده كافي
```

---

## 📊 الإحصائيات والتقارير

### لوحة المشرف (`supervisor_dashboard`)

**بطاقات سريعة:**

- عدد الطلبات المعلقة
- عدد المنتجات غير المفعلة
- عدد طلبات الشحن المعلقة
- عدد التجار الجدد
- عدد تذاكر الدعم المفتوحة

**الرسوم البيانية:**

- مبيعات اليوم
- مبيعات الشهر الحالي
- رسم بياني لآخر 7 أيام

**البيانات:**

```python
sales_today = Order.objects.filter(
    status__in=['PENDING', 'SHIPPED', 'DELIVERED'],
    created_at__date=today
).aggregate(Sum('final_total'))
```

---

## 📱 الإشعارات المتقدمة

### نماذج الإشعارات

1. **Notification** (قاعدة البيانات)
   - رسائل في التطبيق
   - مرئية في لوحة المستخدم

2. **NotificationLog** (سجل الإرسال)
   - تتبع محاولات الإرسال
   - رسائل خطأ في الإرسال

3. **UserFCMToken** (Firebase)
   - توكنات أجهزة المستخدمين
   - دعم أجهزة متعددة
   - Push notifications

### دوال الإشعارات

```python
send_notification(user, title, message, link=None)
    # حفظ في قاعدة البيانات

notify_admins(title, message, link=None)
    # إشعار جميع المشرفين

send_push_to_user(user, title, body)
    # إرسال Push notification عبر Firebase
```

---

## 🆘 نظام الدعم الفني

### تذاكر الدعم (`SupportTicket`)

```python
class SupportTicket:
    Status: OPEN, IN_PROGRESS, RESOLVED, CLOSED
    Priority: LOW, MEDIUM, HIGH

    customer                # من فتح التذكرة
    subject                 # الموضوع
    order                   # مرتبط بطلب (اختياري)
    message                 # الرسالة الأولى
    assigned_to             # المشرف المسؤول
    status, priority
```

### الردود (`TicketMessage`)

```python
class TicketMessage:
    ticket
    sender                  # من أرسل (عميل أو مشرف)
    message
    is_support_reply        # هل رد من الدعم؟
    created_at
```

---

## 📁 هيكل الملفات المرفوعة

```
media/
├── banners/               # صور البانرات
├── categories/            # صور الأقسام (Categories)
├── merchant_ids/          # صور بطاقات التجار
├── products/              # الصور الرئيسية للمنتجات
├── product_gallery/       # صور إضافية للمنتجات
├── shops/                 # صور متاجر التجار
├── promo_popups/          # صور الإعلانات المنبثقة
└── deposits/              # صور إثبات التحويلات البنكية
```

---

## 🏃 المكتبات والأدوات الرئيسية

### Django و REST

- **Django==6.0.2** - الإطار الرئيسي
- **djangorestframework==3.16.1** - REST API
- **rest_framework_simplejwt==5.5.1** - JWT Authentication

### المصادقة والإذن

- **django-allauth==65.14.3** - Google Sign-up
- **django-cors-headers==4.9.0** - CORS support

### قاعدة البيانات

- **psycopg2-binary==2.9.11** - PostgreSQL driver
- **dj-database-url==3.1.2** - DATABASE_URL parsing

### التصميم والميديا

- **pillow==12.1.1** - معالجة الصور
- **django-tinymce==5.0.0** - محرر WYSIWYG
- **django-modeltranslation==0.20.2** - ترجمة النماذج

### الترجمة والدعم

- **django-modeltranslation==0.20.2** - Multilingual

### التكامل الخارجي

- **requests==2.32.5** - HTTP requests
- **firebase_admin==7.2.0** - Firebase Push Notifications
- **google-cloud-storage==3.9.0** - Google Cloud Storage

### الإنتاج

- **gunicorn==25.1.0** - Application server
- **whitenoise==6.11.0** - Static file serving
- **python-dotenv==1.2.1** - Environment variables

---

## ⚙️ إعدادات Django الرئيسية

### المصادقة والتفويض

```python
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'accounts.backends.EmailPhoneUsernameBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
```

### JWT Configuration

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
}
```

### REST Framework

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}
```

### الترجمة والتوطين

```python
LANGUAGE_CODE = 'ar'        # العربية
LANGUAGES = [('ar', 'Arabic'), ('en', 'English')]
TIME_ZONE = 'Africa/Cairo'
USE_TZ = True
```

### CORS

```python
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    'https://elbazaare.com',
    'https://www.elbazaare.com',
]
```

---

## 🗄️ قاعدة البيانات

### المحرك

**التطوير:** SQLite (db.sqlite3)

**الإنتاج:** PostgreSQL

```python
DATABASE_URL=postgresql://user:password@localhost:5432/bazarna_db
```

### الجداول الرئيسية

| الجدول                  | الوصف                   |
| ----------------------- | ----------------------- |
| accounts_user           | المستخدمون والأدوار     |
| accounts_country        | 🔥 الدول                |
| store_product           | المنتجات                |
| store_productsize       | المقاسات والألوان       |
| store_order             | الطلبات                 |
| store_orderitem         | عناصر الطلب             |
| store_merchantprofile   | بيانات التجار           |
| store_wallet            | محافظ التجار            |
| store_wallettransaction | سجل معاملات المحفظة     |
| store_governorate       | المحافظات               |
| store_offer             | العروض والخصومات        |
| store_sitesetting       | 🔥 إعدادات الموقع/الدول |
| support_supportticket   | تذاكر الدعم             |

---

## 🚀 النشر والتشغيل

### الخادم

```bash
gunicorn bazarna.wsgi:application \
  --bind unix:/var/www/bazarna/app.sock \
  --workers 4 \
  --timeout 120
```

### الملفات ذات الصلة

- `Procfile` - تعريفات العمليات
- `runtime.txt` - إصدار Python (3.10.15)
- `.env` - المتغيرات البيئية السرية

### المتغيرات البيئية الحساسة

```env
SECRET_KEY=...
DEBUG=False
DATABASE_URL=...

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Paymob
PAYMOB_API_KEY=...
PAYMOB_INTEGRATION_ID_CARD=...
PAYMOB_INTEGRATION_ID_WALLET=...
PAYMOB_IFRAME_ID=...

# Firebase
FIREBASE_KEY_JSON=...

# Fawaterk
FAWATERK_API_KEY=...
```

---

## 🔗 العلاقات الكاملة

```
User (AbstractUser)
├── country (FK → Country)              # 🔥 جديد
├── merchant_profile (OneToOne)
│   ├── products (Many)
│   │   ├── country (FK → Country)      # 🔥 جديد
│   │   ├── images (Many)
│   │   ├── variations/sizes (Many)
│   │   ├── reviews (Many)
│   │   └── active_offer (OneToOne)
│   ├── wallet (OneToOne)
│   │   ├── transactions (Many)
│   │   └── deposit_transactions (Many)
│   ├── shipping_rates (Many)
│   └── orders (Many)
├── orders (Many)
├── addresses (Many)
├── favorites (Many)
├── referral (Many) [المدعوين]
└── notifications (Many)

Country (🔥 جديد)
├── users
├── products
├── orders
├── governorates
├── site_settings (OneToOne)
├── banners (Many)
├── terms (Many)
├── popups (Many)
└── about_us (Many)

Order
├── items (OrderItem Many)
├── country (FK → Country)              # 🔥 جديد
├── customer (FK → User)
├── merchant (FK → MerchantProfile)
├── governorate (FK → Governorate)      # الآن مرتبط بـ Country
├── return_request (OneToOne)
└── complaint (OneToOne)
```

---

## 📋 ملخص التحديثات الرئيسية

| الميزة           | الحالة القديمة | الحالة الجديدة 🔥     |
| ---------------- | -------------- | --------------------- |
| **دعم الدول**    | دولة واحدة فقط | متعدد الدول           |
| **المحافظات**    | محلي فقط       | مرتبط بكل دولة        |
| **الإعدادات**    | عام واحد       | منفصل لكل دولة        |
| **الأدوار**      | 5 أدوار فقط    | 6 أدوار + مدير دول    |
| **بوابات الدفع** | Paymob فقط     | متعددة (Fawaterk)     |
| **الفلترة**      | عام            | ذكية حسب الدول        |
| **طبقة الخدمات** | موجودة جزئياً  | شاملة (`services.py`) |
| **الإشعارات**    | بسيطة          | متقدمة (FCM, Logs)    |
| **سجل العمليات** | بسيط           | NotificationLog 🆕    |

---

## 🎯 الميزات المستقبلية المقترحة

1. **📱 تطبيق موبايل أصلي** - React Native أو Flutter
2. **🤖 نظام توصيات ذكي** - ML-based recommendations
3. **💬 دردشة مباشرة** - Real-time chat مع الدعم
4. **📦 تتبع الشحن** - Integration مع شركات الشحن
5. **🎯 برنامج الولاء** - Loyalty points system
6. **📊 API تحليلات** - Advanced analytics
7. **⚡ GraphQL API** - بدل REST API
8. **🔔 Webhooks** - لتطبيقات خارجية

---

## ✅ الخلاصة

**Bazarna** الآن منصة **منطورة وجاهزة للتوسع** مع دعم كامل لـ:

✨ **متعددة الدول** - إدارة أسواق متعددة بفعالية
✨ **أدوار ذكية** - مديري دول ومشرفين منفصلين
✨ **معايير عالية** - أمان، أداء، وسهولة استخدام
✨ **توسعية** - جاهزة لإضافة ميزات جديدة

**الحالة:** 🟢 **منتجة وتشتغل فعلياً على elbazaare.com**

---

**آخر تحديث:** أبريل 20، 2026  
**الإصدار:** Django 6.0.2  
**الحالة:** ✅ قيد الإنتاج النشط
