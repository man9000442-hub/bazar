from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class EmailPhoneUsernameBackend(ModelBackend):
    """
    هذا الكلاس يسمح للمستخدم بتسجيل الدخول باستخدام:
    1. الإيميل
    2. رقم الهاتف (phone_primary)
    3. اسم المستخدم (username)
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # نحاول البحث عن المستخدم بأي من الطرق الثلاثة
            user = User.objects.get(
                Q(username=username) | 
                Q(email=username) | 
                Q(phone_primary=username)
            )
        except User.DoesNotExist:
            return None

        # التحقق من الباسورد وهل المستخدم نشط
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None