from django.urls import path

from .views import (
    AdminBookingDetailView, AdminBookingListView, AdminEventBookingsView, AdminEventDetailView, AdminEventListView,
    AdminEventPerformanceView,
)

urlpatterns = [
    path('events', AdminEventListView.as_view()),
    path('events/<int:pk>', AdminEventDetailView.as_view()),
    path('events/<int:pk>/bookings', AdminEventBookingsView.as_view()),
    path('events/<int:pk>/performance', AdminEventPerformanceView.as_view()),
    path('bookings', AdminBookingListView.as_view()),
    path('bookings/<str:reference>', AdminBookingDetailView.as_view()),
]
