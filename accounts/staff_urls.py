from django.urls import path

from .views import StaffDetailView, StaffListView

urlpatterns = [
    path('staff', StaffListView.as_view()),
    path('staff/<int:pk>', StaffDetailView.as_view()),
]
