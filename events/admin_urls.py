from django.urls import path

from .views import AdminEventDetailView, AdminEventListView

urlpatterns = [
    path('events', AdminEventListView.as_view()),
    path('events/<int:pk>', AdminEventDetailView.as_view()),
]
