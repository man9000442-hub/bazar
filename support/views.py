from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import SupportTicket, TicketMessage
from store.models import Order

@login_required
def my_tickets(request):
    tickets = SupportTicket.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'support/my_tickets.html', {'tickets': tickets})

@login_required
def create_ticket(request):
    if request.method == 'POST':
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        order_id = request.POST.get('order_id')
        
        order = None
        if order_id:
            order = Order.objects.filter(id=order_id, customer=request.user).first()
            
        SupportTicket.objects.create(
            customer=request.user,
            subject=subject,
            message=message,
            order=order
        )
        return redirect('my_tickets')
    
    # نرسل الطلبات ليختار منها
    orders = Order.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'support/create_ticket.html', {'orders': orders})

@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk, customer=request.user)
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            TicketMessage.objects.create(ticket=ticket, sender=request.user, message=message)
            ticket.status = 'OPEN' # إعادة فتح إذا رد العميل
            ticket.save()
            return redirect('ticket_detail', pk=pk)

    return render(request, 'support/ticket_detail.html', {'ticket': ticket})


from django.http import JsonResponse

@login_required
def get_ticket_messages(request, ticket_id):
    # جلب الرسائل للتذكرة
    messages = TicketMessage.objects.filter(ticket_id=ticket_id).order_by('created_at')
    
    data = []
    for msg in messages:
        data.append({
            'sender': 'support' if msg.is_support_reply else 'user',
            'text': msg.message,
            'time': msg.created_at.strftime("%H:%M")
        })
        
    return JsonResponse({'messages': data})