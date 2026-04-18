import os
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
from django.db.models import Q
from accounts.models import User, UserFCMToken, NotificationLog
from store.models import Notification



# ==========================================
# 1. تهيئة الاتصال بفايربيز (يحدث مرة واحدة فقط)
# ==========================================

FIREBASE_KEY_PATH = os.path.join(settings.BASE_DIR, 'firebase-key.json')

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin Initialized Successfully!")
    except Exception as e:
        print(f"⚠️ Error initializing Firebase: {e}")


# ==========================================
# 2. إشعارات الموقع الداخلية (In-App Notifications)
# ==========================================


def send_notification(user, title, message, link=None):
    """
    إنشاء إشعار داخلي يظهر في علامة الجرس داخل الموقع/التطبيق
    """
    if user and user.is_authenticated:
        Notification.objects.create(
            recipient=user,
            title=title,
            message=message,
            link=link
        )

def notify_admins(title, message, link=None):
    """
    إرسال إشعار داخلي لجميع المشرفين والمديرين دفعة واحدة
    """
    # جلب جميع المديرين (بما فيهم المالك ومديري الدول)
    admins = User.objects.filter(
        Q(is_superuser=True) | Q(role__in=['ADMIN_LVL2', 'ADMIN_LVL3', 'COUNTRY_ADMIN', 'OWNER'])
    )
    
    # استخدام bulk_create لسرعة الأداء
    notifications = [
        Notification(recipient=admin, title=title, message=message, link=link) 
        for admin in admins
    ]
    
    if notifications:
        Notification.objects.bulk_create(notifications)


def send_push_to_user(user, title, body):
    try:
        # 1. جلب التوكنز
        user_tokens = list(UserFCMToken.objects.filter(user=user).values_list('token', flat=True))
        
        if not user_tokens:
            print(f"⚠️ المستخدم {user.username} ليس لديه توكن مسجل.")
            return False

        # 2. تجهيز الإشعارات (الطريقة الجديدة المتوافقة مع تحديث فايربيز الأخير)
        messages_list = []
        for token in user_tokens:
            msg = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        channel_id='high_importance_channel',
                        sound='default'
                    ),
                ),
                token=token,
            )
            messages_list.append(msg)

        # 3. إرسال الإشعار بالطريقة الجديدة (send_each)
        response = messaging.send_each(messages_list)
        
        # 🔥 التنظيف التلقائي للتوكنز الميتة
        if response.failure_count > 0:
            for i, res in enumerate(response.responses):
                if not res.success:
                    dead_token = user_tokens[i]
                    UserFCMToken.objects.filter(token=dead_token).delete()
                    print(f"🗑️ تم حذف توكن منتهي للمستخدم {user.username}")

        if response.success_count > 0:
            NotificationLog.objects.create(
                user=user, title=title, status="Success", 
                details=f"تم الإرسال بنجاح لـ {response.success_count} جهاز."
            )
            return True
        else:
            NotificationLog.objects.create(
                user=user, title=title, status="Failed", 
                details=f"فشل الإرسال. تم حذف التوكنز المنتهية."
            )
            return False

    except Exception as e:
        # تسجيل الإيرور لو حصل
        NotificationLog.objects.create(
            user=user, title=title, status="Error", details=str(e)
        )
        print('❌ Error sending push notification:', e)
        return False