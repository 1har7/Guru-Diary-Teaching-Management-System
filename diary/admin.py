from django.contrib import admin

from .models import DiaryEntry, LecturerRequest


@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "entry_type", "audience", "is_important", "lecturer", "title")
    list_filter = ("actor", "entry_type", "audience", "is_important")
    search_fields = ("title", "message", "lecturer__username")
    ordering = ("-created_at",)


@admin.register(LecturerRequest)
class LecturerRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "lecturer", "request_type", "status", "admin_replied_at", "resolved_at")
    list_filter = ("request_type", "status")
    search_fields = ("description", "lecturer__username", "lecturer__email", "admin_reply")
    ordering = ("-created_at",)

# Register your models here.
