from django.urls import path

from .views import AdminEnquiryDetailView, AdminEnquiryListView

urlpatterns = [
    path('enquiries', AdminEnquiryListView.as_view()),
    path('enquiries/<str:reference>', AdminEnquiryDetailView.as_view()),
]
