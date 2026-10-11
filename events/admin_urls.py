from django.urls import path

from .views import AdminBookingDetailView, AdminEventBookingsView, AdminEventDetailView, AdminEventListView

urlpatterns = [
    path('events', AdminEventListView.as_view()),
    path('events/<int:pk>', AdminEventDetailView.as_view()),
    path('events/<int:pk>/bookings', AdminEventBookingsView.as_view()),
    path('bookings/<str:reference>', AdminBookingDetailView.as_view()),
]
