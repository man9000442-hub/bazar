from rest_framework import serializers
from .models import SupportTicket, TicketMessage

class TicketMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.first_name', read_only=True)
    time = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = TicketMessage
        fields = ['id', 'message', 'time', 'is_support_reply', 'sender_name']

class SupportTicketSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    date = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = SupportTicket
        fields = ['id', 'subject', 'message', 'status', 'status_display', 'priority', 'priority_display', 'order', 'date']