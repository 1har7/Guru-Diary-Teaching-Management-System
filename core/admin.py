from django.contrib import admin

from .models import ArchivedTimetableSlot, SemesterArchive, SystemSettings, UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "timetable_view", "time_format", "diary_email_alerts", "diary_only_important", "updated_at")
    list_filter = ("theme", "timetable_view", "time_format", "diary_email_alerts", "diary_only_important")
    search_fields = ("user__username", "user__email")


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ("academic_year", "current_semester", "working_days", "periods_per_day", "lab_duration_periods", "enable_diary_auto_logging", "allow_lecturer_requests", "updated_at")


@admin.register(SemesterArchive)
class SemesterArchiveAdmin(admin.ModelAdmin):
    list_display = ("created_at", "academic_year", "semester", "created_by", "note")
    search_fields = ("academic_year", "note")
    list_filter = ("semester",)


@admin.register(ArchivedTimetableSlot)
class ArchivedTimetableSlotAdmin(admin.ModelAdmin):
    list_display = ("archive", "day", "period", "lecturer_username", "subject_code", "class_code")
    list_filter = ("archive", "day")
    search_fields = ("lecturer_username", "subject_code", "subject_name", "class_code", "class_name")

# Register your models here.
