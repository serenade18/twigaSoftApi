from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'AFRIGULF Exchange admin'
admin.site.site_title = 'AFRIGULF Exchange admin'

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/admin/auth/', include('accounts.urls')),
    path('api/admin/', include('enquiries.admin_urls')),
    path('api/admin/', include('accounts.staff_urls')),
    path('api/admin/', include('dashboard.urls')),
    path('api/admin/', include('events.admin_urls')),
    path('api/', include('events.urls')),
    path('api/enquiries', include('enquiries.urls')),
]

# Uploaded event covers; only in DEBUG (static() returns nothing otherwise).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
