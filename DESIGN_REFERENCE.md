# 🎨 دليل الألوان والتصميم - صفحة تعديل التاجر

## 🎯 نظرة عامة على التصميم

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                   صفحة ملف التاجر الإداري              ┃
┃                     Merchant Admin Panel              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## 🎨 الألوان المستخدمة

### الألوان الرئيسية:

| اللون                | الكود     | الاستخدام                    |
| -------------------- | --------- | ---------------------------- |
| 🔵 أزرق (Primary)    | `#0d6efd` | الأيقونات والعناوين الرئيسية |
| 🟢 أخضر (Success)    | `#198754` | الرسائل الموفقة والتأكيدات   |
| 🔴 أحمر (Danger)     | `#dc3545` | التنبيهات والأخطاء           |
| 🟡 أصفر (Warning)    | `#ffc107` | التحذيرات والتنبيهات الخفيفة |
| 🩶 رمادي (Secondary) | `#6c757d` | النصوص المساعدة والثانوية    |
| ⚪ أبيض (Light)      | `#f8f9fa` | الخلفيات الفاتحة             |
| ⚫ أسود (Dark)       | `#212529` | النصوص الرئيسية              |

### أمثلة الاستخدام:

```html
<!-- أيقونات زرقاء -->
<i class="fas fa-eye text-primary"></i>

<!-- نصوص خضراء -->
<span class="text-success">✓ موجود</span>

<!-- خلفيات رمادية -->
<div class="bg-light"></div>

<!-- أزرار مختلفة -->
<button class="btn btn-primary">حفظ</button>
<button class="btn btn-secondary">إلغاء</button>
```

---

## 🎯 الأيقونات المستخدمة

### أيقونات البطاقات والتنقل:

```
👁️  fa-eye              = عرض البيانات
✏️  fa-edit             = تعديل البيانات
💾 fa-save             = حفظ التعديلات
❌ fa-times            = إلغاء أو إغلاق
✓  fa-check-circle    = تأكيد أو توثيق
🏪 fa-store           = المتجر
📞 fa-phone           = الهاتف
📧 fa-envelope        = البريد الإلكتروني
```

### أيقونات الحقول:

```
📝 fa-pen-to-square   = تعديل
🖼️  fa-image          = صورة
📸 fa-camera         = كاميرا
📤 fa-upload         = رفع ملف
📥 fa-download       = تحميل
```

### أيقونات الحالات:

```
⚠️  fa-exclamation-triangle = تحذير
ℹ️  fa-info-circle          = معلومة
✅ fa-check                  = نجح
❌ fa-times                  = فشل
⏳ fa-hourglass            = قيد الانتظار
```

---

## 📐 النسب والمسافات

### حجم الخط:

```
h1 = 2.5rem   (40px)  - عناوين رئيسية
h4 = 1.5rem   (24px)  - عناوين ثانوية
h6 = 1rem     (16px)  - عناوين فرعية
p  = 1rem     (16px)  - نصوص عادية
small = 0.875rem (14px) - نصوص مساعدة
```

### المسافات:

```
Margin Top:    mb-4 = 1.5rem
Margin Bottom: mb-4 = 1.5rem
Padding:       p-4  = 1.5rem
Gap (بين العناصر): g-4 = 1.5rem
```

### حجم الصور:

```
صورة المتجر: 100px × 100px
بطاقات الأرقام: 150px (عرض متساوٍ)
صور المعاملات: 50px × 50px
```

---

## 🎨 الأنماط (Styles)

### نمط الأزرار:

```html
<!-- زر أساسي (Primary) -->
<button class="btn btn-primary rounded-pill px-4">
  <i class="fas fa-save ms-2"></i>حفظ
</button>

<!-- زر ثانوي (Secondary) -->
<button class="btn btn-secondary rounded-pill px-4">
  <i class="fas fa-times ms-2"></i>إلغاء
</button>

<!-- زر بدون تعبئة -->
<button class="btn btn-outline-primary">خيار</button>
```

### نمط البطاقات:

```html
<!-- بطاقة عادية -->
<div class="card border-0 shadow-sm rounded-4 p-4">
  <h5 class="fw-bold">العنوان</h5>
  <p>المحتوى</p>
</div>

<!-- بطاقة ملونة -->
<div class="card border-0 shadow-sm p-3 bg-success text-white">
  <h4 class="fw-bold">2500</h4>
  <small>الرصيد</small>
</div>
```

### نمط الجداول:

```html
<table class="table align-middle mb-0">
  <thead class="bg-light">
    <tr>
      <th class="ps-4">العمود 1</th>
      <th>العمود 2</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="ps-4 fw-bold">المحتوى</td>
      <td>المحتوى</td>
    </tr>
  </tbody>
</table>
```

---

## 📱 التخطيط والشبكة (Grid)

### النظام الشبكي (Responsive):

```
Desktop (lg):
┌─────────────────────┬──────────────────────┐
│     col-md-4        │     col-md-8         │
│   (البيانات)       │   (الإحصائيات)      │
└─────────────────────┴──────────────────────┘

Tablet (md):
┌────────────┬────────────┬────────────┐
│ col-md-4   │ col-md-4   │ col-md-4   │
└────────────┴────────────┴────────────┘

Mobile (xs):
┌──────────────────────────┐
│     col-12 (100%)       │
│  (تكديس عمودي)         │
└──────────────────────────┘
```

### نسب الأعمدة:

```
- col-md-12 = 100% العرض الكامل
- col-md-8  = 66.66% ثلثي العرض
- col-md-6  = 50% نصف العرض
- col-md-4  = 33.33% ثلث العرض
- col-md-3  = 25% ربع العرض
```

---

## 🎬 الحركات والانتقالات

### الـ Transitions:

```css
/* Fade In/Out */
.fade
.show

/* Tab Animation */
data-bs-toggle="tab"
data-bs-target="#target"
```

### الهوفر (Hover):

```
- أزرار: تتغير الخلفية واللون
- روابط: تتغير إلى لون أفتح
- جداول: صف يتظلل عند المرور
```

---

## 🎨 مثال عملي للألوان

### سيناريو عملي:

```html
<!-- جزء علوي (Header) -->
<div class="bg-light p-4">
  <h4 class="fw-bold text-dark">
    <i class="fas fa-edit text-primary ms-2"></i>تعديل البيانات
  </h4>
</div>

<!-- نموذج -->
<form class="p-4">
  <!-- حقل نصي -->
  <label class="form-label fw-bold small text-muted">
    <i class="fas fa-pen ms-2"></i>أنواع البضاعة
  </label>
  <textarea class="form-control border"></textarea>

  <!-- تنبيه النجاح -->
  <small class="text-success d-block mt-2">
    <i class="fas fa-check-circle ms-1"></i>الصورة موجودة
  </small>

  <!-- أزرار -->
  <div class="d-flex gap-2 mt-4">
    <button class="btn btn-primary rounded-pill">
      <i class="fas fa-save ms-2"></i>حفظ
    </button>
    <button class="btn btn-secondary rounded-pill">
      <i class="fas fa-times ms-2"></i>إلغاء
    </button>
  </div>
</form>
```

---

## 📊 جدول المقارنة

| العنصر       | اللون    | الحجم | الأيقونة |
| ------------ | -------- | ----- | -------- |
| الزر الرئيسي | 🔵 أزرق  | md    | ✅       |
| الزر الثانوي | 🩶 رمادي | md    | ❌       |
| النجاح       | 🟢 أخضر  | small | ✓        |
| التحذير      | 🟡 أصفر  | small | ⚠️       |
| العنوان      | ⚫ أسود  | h6    | ✏️       |
| النص المساعد | 🩶 رمادي | small | ℹ️       |

---

## 🔄 حالات مختلفة

### الحالة 1: البيانات موجودة

```
✅ اللون: أخضر
✅ الأيقونة: fa-check-circle
✅ الرسالة: "الصورة موجودة"
✅ الموضع: تحت الحقل
```

### الحالة 2: حقل مطلوب

```
✅ اللون: أحمر (border-danger)
✅ الأيقونة: fa-exclamation-circle
✅ الرسالة: "هذا الحقل مطلوب"
✅ الموضع: تحت الحقل
```

### الحالة 3: حقل محمي

```
✅ اللون: رمادي (disabled)
✅ الأيقونة: fa-lock
✅ الرسالة: "لا يمكن تعديل"
✅ الموضع: تحت الحقل
```

---

## 🎯 إرشادات التصميم

### ✅ افعل:

```
✅ استخدم الألوان بتناسق
✅ وفر مسافة كافية بين العناصر
✅ استخدم أيقونات واضحة
✅ اختبر على أجهزة مختلفة
✅ احرص على التباين (للقراءة الجيدة)
```

### ❌ لا تفعل:

```
❌ استخدم ألوان كثيرة جداً
❌ تجعل النصوص صغيرة جداً
❌ تستخدم ظلال معقدة
❌ تخلط الأنماط المختلفة
❌ تنسَ الـ Accessibility
```

---

## 📱 نصائح للديزاينر الجديد

### عند إضافة عناصر جديدة:

```
1. اتبع الألوان الموجودة (استخدم palette معرّف)
2. استخدم نفس حجم الخطوط
3. حافظ على المسافات المتناسقة
4. استخدم أيقونات من نفس المجموعة (FontAwesome)
5. اختبر على جميع الأحجام
6. تأكد من التباين للرؤية الجيدة
7. اتبع اتجاه RTL (يمين لليسار)
```

---

## 🎓 أمثلة من المشروع

### مثال 1: علامة التبويب النشطة

```html
<button class="nav-link active text-primary fw-bold">
  <i class="fas fa-eye ms-1"></i> العرض
</button>
```

### مثال 2: بطاقة الإحصائيات

```html
<div class="card border-0 shadow-sm p-3 bg-success text-white">
  <small>الرصيد الحالي</small>
  <h4 class="fw-bold mb-0">2500 ج.م</h4>
</div>
```

### مثال 3: نموذج مع تنبيهات

```html
<div class="mb-3">
  <label class="form-label fw-bold small text-muted">
    <i class="fas fa-image ms-1"></i>صورة المتجر
  </label>
  <input type="file" class="form-control" accept="image/*" />
  <small class="text-success d-block mt-2">
    <i class="fas fa-check-circle ms-1"></i>الصورة موجودة
  </small>
</div>
```

---

## 🎨 أداة اختيار الألوان

### الألوان المستخدمة في Bootstrap 5:

```
Primary:   #0d6efd (أزرق)
Success:   #198754 (أخضر)
Danger:    #dc3545 (أحمر)
Warning:   #ffc107 (أصفر)
Info:      #0dcaf0 (أزرق فاتح)
Light:     #f8f9fa (رمادي فاتح جداً)
Dark:      #212529 (رمادي غامق جداً)
```

---

**ملاحظة**: هذا الدليل يساعد على الحفاظ على الاتساق البصري في المشروع.

**تاريخ الإنشاء**: 24 فبراير 2026 ✅
**الحالة**: جاهز كمرجع للديزاينرز والمطورين 🎨
