from django.conf import settings
from django.db import models


class DiaryEntry(models.Model):
    ACTOR_CHOICES = [
        ("system", "System"),
        ("admin", "Admin"),
    ]

    TYPE_CHOICES = [
        ("timetable_generation_started", "Timetable generation started"),
        ("timetable_generation_completed", "Timetable generation completed"),
        ("timetable_regenerated", "Timetable regenerated"),
        ("timetable_updated", "Timetable updated"),
        ("subject_assigned", "Subject assigned"),
        ("subject_rejected", "Subject rejected"),
        ("clash_detected", "Timetable clash detected"),
        ("announcement", "Announcement"),
        ("progress_reminder_50", "Progress reminder (50%)"),
        ("progress_reminder_75", "Progress reminder (75%)"),
        ("progress_reminder_end_soon", "Progress reminder (end approaching)"),
        ("weekly_summary", "Weekly summary"),
    ]

    AUDIENCE_CHOICES = [
        ("lecturers", "Lecturers"),
        ("admins", "Admins"),
        ("both", "Both"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=20, choices=ACTOR_CHOICES, default="system")
    entry_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default="lecturers")

    title = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(blank=True, default="")
    is_important = models.BooleanField(default=False)
    meta = models.JSONField(blank=True, default=dict)

    # If set, the entry is specific to that lecturer; otherwise it's global (e.g., announcements).
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diary_entries",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = self.lecturer.username if self.lecturer else "All"
        return f"[{self.actor}] {self.entry_type} ({who})"


class LecturerRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ("timetable_clash", "Timetable clash"),
        ("subject_change", "Subject change"),
        ("leave_unavailability", "Leave / unavailability"),
        ("other_academic_issue", "Other academic issue"),
    ]

    STATUS_CHOICES = [
        ("open", "Open"),
        ("seen", "Seen"),
        ("resolved", "Resolved"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="diary_requests",
    )
    request_type = models.CharField(max_length=40, choices=REQUEST_TYPE_CHOICES)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    seen_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Admin can reply once; keep immutable afterwards.
    admin_reply = models.TextField(blank=True, default="")
    admin_replied_at = models.DateTimeField(null=True, blank=True)
    admin_replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="diary_replies",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.lecturer.username}: {self.request_type} ({self.status})"

# Create your models here.
