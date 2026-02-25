# 📱 مشروع Bazarna - ملخص شامل

## 🎯 نظرة عامة على المشروع

**Bazarna** هو منصة تجارة إلكترونية **B2C** (متعددة التجار) مكتوبة بـ **Django 6.0** و **PostgreSQL** وتستضاف على **Linux** مع **Gunicorn**.

موقع الإنتاج: `elbazaare.com` و `www.elbazaare.com`

---

## 🏗️ بنية المشروع

```
bazarna/              # إعدادات المشروع الرئيسية
├── settings.py       # إعدادات Django
├── urls.py          # الروابط الرئيسية
├── wsgi.py          # ملف WSGI للـ Gunicorn
└── asgi.py          # ملف ASGI

accounts/            # تطبيق المستخدمين والمصادقة
├── models.py        # User, CustomRole, Address
├── backends.py      # مصادقة مخصصة (Email/Phone)
├── adapters.py      # محولات Google Sign-up
├── middleware.py    # فحص الحظر (BanMiddleware)
├── forms.py         # نماذج مخصصة
└── urls.py          # روابط الحسابات

store/               # تطبيق المتجر والمنتجات
├── models.py        # المنتجات، الطلبات، المحافظ، إلخ
├── views.py         # صفحات المتجر الرئيسية
├── api_views.py     # API للتطبيقات
├── serializers.py   # Serializers للـ REST
├── paymob_utils.py  # تكامل Paymob للدفع
├── sitemaps.py      # خريطة الموقع للـ SEO
└── signals.py       # الإشارات المخصصة

merchant_panel/      # لوحة التحكم للتجار
├── views.py         # إدارة المنتجات والطلبات والمحفظة
├── urls.py
└── models.py

supervisor/          # لوحة الإشراف (Admin)
└── views.py

support/             # نظام الدعم الفني
├── models.py        # تذاكر الدعم
├── views.py
└── urls.py

templates/           # القوالب HTML
├── base.html
├── store/          # قوالب المتجر
├── account/        # قوالب الحسابات
├── merchant/       # قوالب لوحة التاجر
└── support/        # قوالب الدعم

static/              # ملفات ثابتة (CSS, JS)
media/               # الصور المرفوعة
staticfiles/         # ملفات ثابتة مضغوطة للإنتاج
```

---

## 👥 أنواع المستخدمين

### 1️⃣ **العميل (CUSTOMER)**

- يتصفح المنتجات
- ينشئ سلة التسوق
- يضع الطلبات
- يختار طرق الدفع (كاش، بطاقة، محفظة)
- يُقيّم المنتجات بعد التسليم

### 2️⃣ **التاجر (MERCHANT)**

- ينشئ متجره الخاص
- يرفع المنتجات بمقاسات وألوان مختلفة
- يدير المحفظة (الرصيد)
- يشحن رصيده بـ Paymob
- يسحب أرباحه
- يعرض عروضاً على منتجاته
- يراقب طلباته

### 3️⃣ **المشرف درجة 2 (ADMIN_LVL2)**

- يراجع طلبات التجار الجدد
- يوافق/يرفض تسجيل التجار
- ينشر عروضاً من المنصة

### 4️⃣ **المشرف درجة 3 (ADMIN_LVL3)**

- يدير تذاكر الدعم الفني
- يراقب الشكاوى والمرتجعات

### 5️⃣ **المالك (OWNER)**

- صاحب المنصة الأساسي
- وصول كامل لـ Django Admin

---

## 💰 نظام المحفظة والدفع

### المحفظة (Wallet)

```
User (تاجر) → MerchantProfile → Wallet (الرصيد)
```

**الرصيد يتغير عند:**

- ✅ بيع منتج → إضافة (السعر - العمولة)
- ✅ شحن رصيد → إضافة
- ✅ سحب أرباح → خصم
- ❌ مرتجع منتج → خصم
- 🔸 معاملات معلقة أثناء النزاعات

### المعاملات (WalletTransaction)

كل تغيير في الرصيد يُسجل في سجل:

- **SALE**: ربح من بيع منتج
- **PENDING**: رصيد معلق (في الحجز)
- **COMPENSATION**: شحن أو تعويض
- **WITHDRAWAL**: سحب أرباح
- **REFUND**: خصم من مرتجع

---

## 📦 نظام الطلبات (Orders)

### حالات الطلب

```
CART → WAITING_PAYMENT → PENDING → APPROVED → SHIPPED → DELIVERED → [تقييم]
                                                                    ↓
                                                    is_confirmed_by_customer
```

| الحالة              | الوصف                        |
| ------------------- | ---------------------------- |
| **CART**            | في السلة (لم يُنهِ الشراء)   |
| **WAITING_PAYMENT** | بانتظار الدفع الإلكتروني     |
| **PENDING**         | قيد الانتظار (انتظار التاجر) |
| **APPROVED**        | وافق التاجر على الطلب        |
| **SHIPPED**         | تم الشحن                     |
| **DELIVERED**       | وصل للعميل                   |
| **RETURNED**        | مرتجع                        |
| **CANCELLED**       | ملغى                         |

### حساب الأسعار

```
final_total = total_products_price + shipping_cost + platform_fees - referral_discount
```

**عمولة المنصة (Platform Fees):**

- ثابتة: 3 ج.م
- نسبة: 2.75%
- تُضاف فقط عند الدفع الإلكتروني

**الشحن:**

- سعر مختلف حسب المحافظة والتاجر
- شحن مجاني للطلب الأول
- شحن مجاني عند شراء X قطعة (حسب العرض)

---

## 🎁 نظام الدعوات (Referral System)

### كيف يعمل؟

```
User A (يدعو) → يعطي رابطه → User B (يسجل)
                                    ↓
                        User B يشتري منتجات
                                    ↓
User A يحصل على مكافأة | User B يحصل على خصم
```

### الحقول المتعلقة (في User):

- `referral_code`: كود دعوة فريد (8 حروف عشوائية)
- `invited_by`: من دعاه
- `referral_balance`: رصيد المكافآت المتراكمة

### إعدادات (في SiteSetting):

- `referral_reward_amount`: قيمة المكافأة = 50 ج.م
- `referral_grace_period_hours`: مهلة إدخال الكود = 24 ساعة
- `referral_reward_limit_orders`: عدد الطلبات المؤهلة = 1
- `referral_discount_limit_pct`: أقصى خصم لكل منتج = 10%

---

## 💳 نظام الدفع (Paymob Integration)

### طرق الدفع المدعومة

1. **COD (Cash on Delivery)** - الدفع عند الاستلام
2. **ONLINE** - بطاقة بنكية (Visa/Mastercard) عبر Paymob
3. **WALLET** - محفظة إلكترونية (فودافون كاش، إتصالات، وي)

### تدفق الدفع (Paymob)

```
1. المستخدم → يختار طريقة الدفع
2. Backend → يحصل على Token من Paymob
3. Backend → ينشئ طلب دفع (Order)
4. Backend → يحصل على Payment Key
5. Frontend → يفتح Iframe (للبطاقة) أو يوجه الرابط (للمحفظة)
6. المستخدم → يدخل البيانات
7. Paymob → يرد إلى Callback URL
8. Backend → يحدث الطلب والرصيد
```

### ملفات Paymob

- `store/paymob_utils.py`: فئة `PaymobManager` للتعامل مع الـ API
  - `get_token()`: الحصول على توكن المصادقة
  - `create_order()`: إنشاء طلب دفع
  - `get_payment_key()`: مفتاح الدفع
  - `pay_with_wallet()`: دفع محفظة إلكترونية

### Callbacks

- **عملاء**: `/payment_callback/` - معالجة دفع الطلبات
- **تجار**: `/merchant/paymob-callback/` - معالجة شحن الرصيد

---

## 🛍️ نظام المنتجات

### هيكل المنتج

```
Product
├── name, description, base_price
├── category (ForeignKey)
├── merchant (ForeignKey لـ MerchantProfile)
├── image (الصورة الرئيسية)
├── ProductImage (صور إضافية)
├── ProductSize/variations (مقاسات وألوان وكميات)
├── Offer (عروض)
└── reviews (التقييمات)
```

### المقاسات والكميات (ProductSize)

```
- size_label: S, M, L
- color_label: أحمر، أزرق
- stock_quantity: الكمية المتاحة
```

### العروض (Offer)

- نسبة خصم على منتج
- صلاحية محددة
- شحن مجاني (اختياري)
- عرض من المنصة أم التاجر؟

---

## ⚙️ إعدادات الموقع (SiteSetting)

جدول واحد فقط يحتوي على:

- اسم الموقع
- رسوم المنصة (ثابتة + نسبة)
- الحد الأدنى للسحب
- المبلغ المحجوز في المحفظة (لا يمكن سحبه)
- الحد الأدنى لتفعيل المنتجات
- إعدادات الدعوات
- إعدادات البانر

---

## 📱 المصادقة والأمان

### طرق المصادقة

1. **Email/Username** - التقليدية
2. **Phone** - رقم هاتف
3. **Google Sign-up** - عبر django-allauth

### المصادقة المخصصة

- `accounts.backends.EmailPhoneUsernameBackend`
- يتقبل: Email، Username، أو Phone
- يتحقق من الهيوية تلقائياً

### الحظر (Ban System)

- حقل `is_banned` في جدول User
- Middleware `BanMiddleware` يفحصه
- إذا كان محظور → يُعاد لصفحة banned.html

### الأمان

```python
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

---

## 🔍 البحث والتصفية

في الصفحة الرئيسية:

- بحث حسب اسم المنتج أو الوصف
- تصفية حسب القسم
- عرض المنتجات النشطة فقط
- شرط إضافي: رصيد التاجر ≥ الحد الأدنى

---

## 📊 إحصائيات وتقارير

### في لوحة التاجر

- عدد الطلبات
- إجمالي المبيعات
- الرصيد الحالي
- الأرباح المعلقة
- الطلبات المرتجعة

### في لوحة الإشراف

- عمليات الشحن المعلقة
- التجار الجدد
- المشاكل والنزاعات

---

## 📧 الإشعارات (Notification)

جدول لتسجيل الإشعارات:

- `recipient`: من يتلقى الإشعار
- `title`: العنوان
- `message`: الرسالة
- `is_read`: هل قُرئ؟
- `link`: رابط التوجيه (اختياري)

---

## 📝 الدعم الفني (Support)

### تذاكر الدعم (SupportTicket)

- حالات: مفتوح، قيد المعالجة، تم الحل، مغلق
- أولويات: عادية، متوسطة، عاجلة
- قد تكون مرتبطة بطلب معين
- يمكن تعيينها لمشرف

### الردود (TicketMessage)

- رسائل ثنائية الاتجاه
- من العميل أو من الدعم
- مسجلة بالتاريخ

---

## 🗄️ قاعدة البيانات

### محرك قاعدة البيانات

```
PostgreSQL
- Host: localhost
- Port: 5432
- Database: bazarna_db
- User: bazarna_user
- Password: BazarnaPass2024
```

### جداول رئيسية

1. **accounts_user**: المستخدمون
2. **store_product**: المنتجات
3. **store_productsize**: المقاسات والكميات
4. **store_order**: الطلبات
5. **store_orderitem**: عناصر الطلب
6. **store_merchantprofile**: بيانات التاجر
7. **store_wallet**: محافظ التجار
8. **store_wallettransaction**: سجل المعاملات
9. **store_offer**: العروض
10. **support_supportticket**: تذاكر الدعم

---

## 📁 المسارات المهمة

### الصور المرفوعة (Media)

```
media/
├── banners/           # صور البانرات
├── categories/        # صور الأقسام
├── merchant_ids/      # صور البطاقات الشخصية
├── product_gallery/   # صور المنتجات الإضافية
├── products/          # الصور الرئيسية للمنتجات
└── shops/             # صور متاجر التجار
```

### الملفات الثابتة

```
staticfiles/           # مضغوطة ومخدومة من Whitenoise
static/                # المصدر الأصلي (CSS, JS)
```

---

## 🚀 آليات التشغيل

### الخادم

```bash
gunicorn bazarna.wsgi:application --bind unix:/var/www/bazarna/app.sock
```

### الملفات المرتبطة

- `Procfile`: تعريفات العمليات
- `gunicorn.ctl`: أداة التحكم بـ Gunicorn
- `runtime.txt`: إصدار Python

---

## 🔐 الحقول الحساسة (في .env)

```
DATABASE_URL=...
SECRET_KEY=django-insecure-...
DEBUG=False (في الإنتاج)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
PAYMOB_API_KEY=...
PAYMOB_INTEGRATION_ID_CARD=...
PAYMOB_INTEGRATION_ID_WALLET=...
PAYMOB_IFRAME_ID=...
```

---

## ⚡ المكتبات الرئيسية

```
Django==6.0.2
djangorestframework==3.16.1
django-allauth==65.14.3
django-cors-headers==4.9.0
psycopg2-binary==2.9.11
pillow==12.1.1
gunicorn==25.1.0
whitenoise==6.11.0
requests==2.32.5
```

---

## 🎨 الميزات الإضافية

### Sitemap (خريطة الموقع)

- لتحسين الـ SEO
- في `store/sitemaps.py`

### CORS Headers

- للسماح بطلبات من تطبيقات خارجية
- كل التطبيقات مسموح حالياً

### WhiteNoise

- تقديم الملفات الثابتة بدون خادم ويب منفصل
- مهم في الإنتاج

### Context Processors

- `store.context_processors.site_settings`
- يوفر إعدادات الموقع لكل قالب

---

## 📱 التطبيق الآخر (supervisor)

تطبيق فارغ حالياً، يبدو أنه مخطط للإشراف المتقدم.

---

## 🔄 العلاقات الرئيسية

```
User (AbstractUser)
├── merchant_profile (OneToOne)
│   ├── products (Many)
│   │   ├── images (Many)
│   │   ├── variations/sizes (Many)
│   │   ├── reviews (Many)
│   │   └── offers (OneToOne)
│   ├── wallet (OneToOne)
│   │   ├── transactions (Many)
│   │   └── shipping_rates (Many)
│   └── orders (Many)
├── orders (Many)
├── addresses (Many)
├── favorites (Many)
├── invitees (Many) [الدعوات]
└── notifications (Many)

Order
├── items (OrderItem Many)
├── customer (User)
├── merchant (MerchantProfile)
└── governorate (Governorate)
```

---

## 📋 الملخص السريع

| الجانب             | الوصف                              |
| ------------------ | ---------------------------------- |
| **النوع**          | منصة تجارة إلكترونية متعددة التجار |
| **الإطار**         | Django 6.0                         |
| **قاعدة البيانات** | PostgreSQL                         |
| **الخادم**         | Gunicorn + Nginx (على Linux)       |
| **الدفع**          | Paymob (البطاقة والمحفظة)          |
| **المصادقة**       | Email/Phone/Username/Google        |
| **الدعوات**        | نظام مكافآت للتسويق                |
| **المنتجات**       | مقاسات وألوان وكميات متعددة        |
| **الطلبات**        | متابعة من الطلب للتسليم والتقييم   |
| **لوحات التحكم**   | تاجر، إشراف، دعم فني               |

---

## 🎯 الخطوات التالية (المقترحة)

1. ✅ فهم البنية الحالية (تم)
2. 🔄 اختبار العمليات الأساسية
3. 🐛 البحث عن الأخطاء والمشاكل
4. ⚡ تحسين الأداء
5. 🔐 تدقيق الأمان
6. 📈 إضافة ميزات جديدة

---

**آخر تحديث**: فبراير 24، 2026
**الإصدار**: Django 6.0.2
**الحالة**: قيد الإنتاج الفعلي ✅
