from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import SupportTicket, TicketMessage
from .serializers import SupportTicketSerializer, TicketMessageSerializer
from store.models import Order

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_tickets_api(request):
    """جلب قائمة التذاكر الخاصة بالمستخدم"""
    tickets = SupportTicket.objects.filter(customer=request.user).order_by('-created_at')
    return Response({
        'status': 'success', 
        'tickets': SupportTicketSerializer(tickets, many=True).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_ticket_api(request):
    """إنشاء تذكرة جديدة"""
    subject = request.data.get('subject')
    message = request.data.get('message')
    order_id = request.data.get('order_id')

    if not subject or not message:
        return Response({'status': 'error', 'message': 'الموضوع والرسالة مطلوبان'}, status=status.HTTP_400_BAD_REQUEST)

    order = None
    if order_id:
        try:
            # ربط التذكرة بطلب إذا كان موجوداً ويخص هذا المستخدم
            order = Order.objects.get(id=order_id, user=request.user) 
        except Order.DoesNotExist:
            pass

    ticket = SupportTicket.objects.create(
        customer=request.user,
        subject=subject,
        message=message,
        order=order
    )
    
    return Response({'status': 'success', 'message': 'تم إنشاء التذكرة بنجاح', 'ticket_id': ticket.id}, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ticket_detail_api(request, ticket_id):
    """عرض تفاصيل التذكرة مع الردود السابقة"""
    try:
        ticket = SupportTicket.objects.get(id=ticket_id, customer=request.user)
        messages_qs = TicketMessage.objects.filter(ticket=ticket).order_by('created_at')
        
        return Response({
            'status': 'success',
            'ticket': SupportTicketSerializer(ticket).data,
            'messages': TicketMessageSerializer(messages_qs, many=True).data
        })
    except SupportTicket.DoesNotExist:
        return Response({'status': 'error', 'message': 'التذكرة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reply_ticket_api(request, ticket_id):
    """إرسال رد جديد من العميل داخل التذكرة"""
    message = request.data.get('message')
    if not message:
        return Response({'status': 'error', 'message': 'الرسالة مطلوبة'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        ticket = SupportTicket.objects.get(id=ticket_id, customer=request.user)
        TicketMessage.objects.create(ticket=ticket, sender=request.user, message=message)
        
        # إعادة فتح التذكرة تلقائياً إذا كانت مغلقة
        if ticket.status != 'OPEN':
            ticket.status = 'OPEN'
            ticket.save()
            
        return Response({'status': 'success', 'message': 'تم إرسال الرد بنجاح'})
    except SupportTicket.DoesNotExist:
        return Response({'status': 'error', 'message': 'التذكرة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)