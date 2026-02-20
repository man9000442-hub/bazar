from django.db import models
from django.conf import settings
from store.models import Order

class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "مفتوحة"
        IN_PROGRESS = "IN_PROGRESS", "قيد المعالجة"
        RESOLVED = "RESOLVED", "تم الحل"
        CLOSED = "CLOSED", "مغلقة"

    class Priority(models.TextChoices):
        LOW = "LOW", "عادية"
        MEDIUM = "MEDIUM", "متوسطة"
        HIGH = "HIGH", "عاجلة"

    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tickets')
    subject = models.CharField(max_length=200, verbose_name="الموضوع")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="رقم الطلب (اختياري)")
    message = models.TextField(verbose_name="الرسالة")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # من المشرف الذي يتابعها؟
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')

    def __str__(self):
        return f"#{self.id} - {self.subject}"

# الردود على التذاكر
class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # هل هي رد من الدعم أم من العميل؟
    is_support_reply = models.BooleanField(default=False)