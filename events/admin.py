from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'location', 'period', 'is_published', 'sort_order']
    list_editable = ['is_published', 'sort_order']
    list_filter = ['is_published']
    search_fields = ['title', 'organiser', 'location']
    prepopulated_fields = {'slug': ['title']}
