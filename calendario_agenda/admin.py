from django.contrib import admin
from .models import CalendarEvent

@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ("title","start","end","source","source_label","empresa_nome","all_day")
    list_filter = ("source","all_day")
    search_fields = ("title","description","source_label","empresa_nome")
