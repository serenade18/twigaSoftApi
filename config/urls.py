from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'AFRIGULF Exchange admin'
admin.site.site_title = 'AFRIGULF Exchange admin'

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/admin/auth/', include('accounts.urls')),
    path('api/admin/', include('enquiries.admin_urls')),
    path('api/events', include('events.urls')),
    path('api/enquiries', include('enquiries.urls')),
]
