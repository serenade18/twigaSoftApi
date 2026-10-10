from django.urls import path

from . import views

urlpatterns = [
    path('login', views.LoginView.as_view()),
    path('logout', views.LogoutView.as_view()),
    path('me', views.MeView.as_view()),
    path('forgot-password', views.ForgotPasswordView.as_view()),
    path('reset-password', views.ResetPasswordView.as_view()),
]
