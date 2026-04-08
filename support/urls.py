from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    # API endpoints
    path('api/tickets/', api_views.customer_tickets_api, name='api_customer_tickets'),
    path('api/tickets/new/', api_views.create_ticket_api, name='api_create_ticket'),
    path('api/tickets/<int:ticket_id>/', api_views.ticket_detail_api, name='api_ticket_detail'),
    path('api/tickets/<int:ticket_id>/reply/', api_views.reply_ticket_api, name='api_reply_ticket'),

    # Template endpoints
    path('', views.my_tickets, name='my_tickets'),
    path('new/', views.create_ticket, name='create_ticket'),
    path('<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('api/messages/<int:ticket_id>/', views.get_ticket_messages, name='get_ticket_messages'),
]