from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # إذا كان المستخدم يربط حسابه وهو مسجل دخول أصلاً، لا نفعل شيئاً
        if sociallogin.is_existing:
            return

        # البحث عن مستخدم بنفس الإيميل
        email = sociallogin.account.extra_data.get('email')
        if not email:
            return

        User = get_user_model()
        try:
            # إذا وجدنا مستخدماً بهذا الإيميل
            user = User.objects.get(email=email)
            # نقوم بربط حساب جوجل بهذا المستخدم فوراً
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass # لا يوجد مستخدم، سيقوم allauth بإنشاء واحد جديد

from allauth.account.adapter import DefaultAccountAdapter

class MyAccountAdapter(DefaultAccountAdapter):
    def get_client_ip(self, request):
        # نرجع IP وهمي لتجاوز الخطأ
        return "127.0.0.1"