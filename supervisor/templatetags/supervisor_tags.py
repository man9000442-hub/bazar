from django import template

register = template.Library()

@register.filter(name='has_perm')
def has_perm(user, perm_name):
    """فلتر مخصص للتحقق من صلاحيات المشرف داخل قوالب الـ HTML"""
    return user.has_perm_access(perm_name)