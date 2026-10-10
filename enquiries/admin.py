from django.contrib import admin

from .models import Enquiry


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ['reference', 'name', 'email', 'country', 'interest', 'status', 'created_at']
    list_filter = ['status', 'interest', 'created_at']
    search_fields = ['reference', 'name', 'email', 'country', 'message']
    readonly_fields = ['reference', 'name', 'email', 'phone', 'country', 'interest', 'message', 'ip_address', 'created_at']
    fields = readonly_fields[:-2] + ['status', 'notes', 'ip_address', 'created_at']

    def has_add_permission(self, request):
        return False
