from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'location', 'start_date', 'is_published', 'sort_order']
    list_editable = ['is_published', 'sort_order']
    list_filter = ['is_published', 'category', 'location']
    search_fields = ['title', 'organiser', 'location']
    prepopulated_fields = {'slug': ['title']}
    readonly_fields = ['created_at', 'updated_at']
