from django.urls import path
from . import views

urlpatterns = [
    path('', views.my_tickets, name='my_tickets'),
    path('new/', views.create_ticket, name='create_ticket'),
    path('<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('api/messages/<int:ticket_id>/', views.get_ticket_messages, name='get_ticket_messages'),
]