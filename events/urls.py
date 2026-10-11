from django.urls import path

from .views import EventBookingView, EventDetailView, EventListView, EventViewCountView, TicketsPdfView, TicketsView

urlpatterns = [
    path('events', EventListView.as_view()),
    path('events/<slug:slug>', EventDetailView.as_view()),
    path('events/<slug:slug>/view', EventViewCountView.as_view()),
    path('events/<slug:slug>/bookings', EventBookingView.as_view()),
    path('tickets/<str:token>', TicketsView.as_view()),
    path('tickets/<str:token>/pdf', TicketsPdfView.as_view()),
]
