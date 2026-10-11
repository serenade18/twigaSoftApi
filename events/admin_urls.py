from django.urls import path

from .views import (
    AdminBookingDetailView, AdminBookingListView, AdminEventBookingsView, AdminEventDetailView, AdminEventListView,
    AdminEventPerformanceView, AdminResendTicketsView, CheckInView,
)

urlpatterns = [
    path('events', AdminEventListView.as_view()),
    path('events/<int:pk>', AdminEventDetailView.as_view()),
    path('events/<int:pk>/bookings', AdminEventBookingsView.as_view()),
    path('events/<int:pk>/performance', AdminEventPerformanceView.as_view()),
    path('bookings', AdminBookingListView.as_view()),
    path('bookings/<str:reference>', AdminBookingDetailView.as_view()),
    path('bookings/<str:reference>/resend-tickets', AdminResendTicketsView.as_view()),
    path('check-in', CheckInView.as_view()),
]
