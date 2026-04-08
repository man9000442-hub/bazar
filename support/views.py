# ==========================================
# 1. الاستدعاءات الأساسية (Imports)
# ==========================================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse

# الموديلات
from .models import SupportTicket, TicketMessage
from store.models import Order

# ==========================================
# إعداد دوال الإشعارات (الداخلية والموبايل)
# ==========================================
try:
    from store.utils import send_notification, notify_admins
except ImportError:
    def send_notification(user, title, message, link=None): pass
    def notify_admins(title, message, link=None): pass

# 🔥 استدعاء دالة إشعارات الموبايل (Push Notifications) الجديدة
try:
    from store.utils import send_push_to_user 
except ImportError:
    def send_push_to_user(user, title, body): pass


# ==========================================
# 2. دوال الدعم الفني (Support Views)
# ==========================================

@login_required
def my_tickets(request):
    """عرض قائمة تذاكر الدعم الفني الخاصة بالمستخدم"""
    tickets = SupportTicket.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'support/my_tickets.html', {'tickets': tickets})


@login_required
def create_ticket(request):
    """إنشاء تذكرة دعم فني جديدة من قبل العميل/التاجر"""
    if request.method == 'POST':
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        order_id = request.POST.get('order_id')
        
        order = None
        if order_id:
            order = Order.objects.filter(id=order_id, customer=request.user).first()
            
        ticket = SupportTicket.objects.create(
            customer=request.user,
            subject=subject,
            message=message,
            order=order
        )
        
        # --- [إشعار داخلي طمأنة للعميل] ---
        send_notification(
            user=request.user,
            title="تم استلام طلبك 🎫",
            message=f"لقد استلمنا تذكرتك بعنوان '{subject}'. فريق الدعم سيقوم بمراجعتها والرد في أقرب وقت.",
            link=f"/support/ticket/{ticket.id}/"
        )

        # 🔥 --- [إشعار الموبايل Push Notification للعميل] ---
        send_push_to_user(
            user=request.user,
            title="تذكرتك وصلتنا 🎫",
            body=f"استلمنا رسالتك بخصوص '{subject}' والدعم الفني هيتواصل معاك قريب جداً."
        )

        # 🔥 --- [إشعار للإدارة بوجود تذكرة جديدة] ---
        notify_admins(
            title="تذكرة دعم فني جديدة 🚨",
            message=f"قام المستخدم {request.user.first_name} بفتح تذكرة جديدة: {subject}.",
            link=reverse('super_ticket_detail', args=[ticket.id]) # توجيه المشرف لصفحة التذكرة في لوحة الإدارة
        )
        
        messages.success(request, "تم إرسال تذكرتك بنجاح، سيقوم الدعم الفني بالتواصل معك قريباً.")
        return redirect('my_tickets')
    
    # نرسل الطلبات ليختار منها في حال كانت الشكوى تخص طلباً معيناً
    orders = Order.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'support/create_ticket.html', {'orders': orders})


@login_required
def ticket_detail(request, pk):
    """عرض تفاصيل التذكرة وإرسال الردود من قبل العميل"""
    ticket = get_object_or_404(SupportTicket, pk=pk, customer=request.user)
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            TicketMessage.objects.create(ticket=ticket, sender=request.user, message=message)
            
            # إعادة فتح التذكرة تلقائياً إذا كانت مغلقة وقام العميل بالرد
            if ticket.status != 'OPEN':
                ticket.status = 'OPEN' 
                ticket.save()
            
            # 🔥 --- [إشعار للإدارة بوجود رد من العميل] ---
            notify_admins(
                title="رد جديد من عميل 📩",
                message=f"أرسل {request.user.first_name} رداً جديداً على التذكرة #{ticket.id}.",
                link=reverse('super_ticket_detail', args=[ticket.id])
            )
                
            messages.success(request, "تم إرسال ردك بنجاح.")
            return redirect('ticket_detail', pk=pk)

    return render(request, 'support/ticket_detail.html', {'ticket': ticket})


@login_required
def get_ticket_messages(request, ticket_id):
    """API لجلب رسائل التذكرة وتحديث الشات برمجياً (AJAX)"""
    # التأكد من أن التذكرة تخص المستخدم نفسه للحماية من التطفل
    ticket = get_object_or_404(SupportTicket, id=ticket_id, customer=request.user)
    
    # جلب الرسائل للتذكرة
    messages_qs = TicketMessage.objects.filter(ticket=ticket).order_by('created_at')
    
    data = []
    for msg in messages_qs:
        data.append({
            'sender': 'support' if msg.is_support_reply else 'user',
            'text': msg.message,
            'time': msg.created_at.strftime("%H:%M")
        })
        
    return JsonResponse({'messages': data})