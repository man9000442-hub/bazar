def mobile_app_detector(request):
    """
    هذه الدالة تفحص نوع المتصفح (User-Agent).
    في فلاتر، سنقوم ببرمجة التطبيق ليرسل كلمة 'ElbazaarApp' 
    للتعرف عليه وإخفاء قوائم الويب.
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    # إذا كانت الكلمة موجودة، إذن المستخدم يفتح من التطبيق
    is_mobile_app = 'ElbazaarApp' in user_agent
    
    return {
        'is_mobile_app': is_mobile_app
    }