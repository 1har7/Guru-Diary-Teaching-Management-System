from django.conf import settings
from django.db import models


class UserPreference(models.Model):
    THEME_CHOICES = [
        ("light", "Light"),
        ("dark", "Dark"),
    ]
    TIMETABLE_VIEW_CHOICES = [
        ("grid", "Grid"),
        ("list", "List"),
    ]
    TIME_FORMAT_CHOICES = [
        ("12h", "12-hour"),
        ("24h", "24-hour"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prefs")
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="light")
    timetable_view = models.CharField(max_length=10, choices=TIMETABLE_VIEW_CHOICES, default="grid")
    time_format = models.CharField(max_length=10, choices=TIME_FORMAT_CHOICES, default="24h")

    diary_email_alerts = models.BooleanField(default=False)
    diary_only_important = models.BooleanField(default=False)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Prefs({self.user.username})"


class SystemSettings(models.Model):
    """
    Singleton-like settings row used by the Admin Settings tab.
    Keep as a normal model so it can be managed in Django Admin too.
    """

    academic_year = models.CharField(max_length=20, blank=True, default="")
    current_semester = models.IntegerField(default=1)
    semester_start_date = models.DateField(null=True, blank=True)
    semester_end_date = models.DateField(null=True, blank=True)

    working_days = models.CharField(max_length=20, default="mon-sat")  # "mon-fri" or "mon-sat"
    periods_per_day = models.IntegerField(default=6)
    period_duration_minutes = models.IntegerField(default=60)
    break_period_position = models.IntegerField(default=0)  # 0 => disabled; else period number after which break occurs

    max_hours_per_lecturer_per_week = models.IntegerField(default=0)  # 0 => no limit enforced yet
    lab_duration_periods = models.IntegerField(default=2)  # 1 or 2
    allow_consecutive_labs = models.BooleanField(default=True)
    clear_existing_before_regen = models.BooleanField(default=True)

    enable_diary_auto_logging = models.BooleanField(default=True)
    allow_lecturer_requests = models.BooleanField(default=True)
    admin_email_for_alerts = models.EmailField(blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "SystemSettings"


class SemesterArchive(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="archives_created"
    )

    academic_year = models.CharField(max_length=20)
    semester = models.IntegerField()
    semester_start_date = models.DateField(null=True, blank=True)
    semester_end_date = models.DateField(null=True, blank=True)

    note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.academic_year} - Sem {self.semester}"


class ArchivedTimetableSlot(models.Model):
    archive = models.ForeignKey(SemesterArchive, on_delete=models.CASCADE, related_name="slots")
    day = models.CharField(max_length=20, blank=True, default="")
    period = models.IntegerField(null=True, blank=True)
    time_slot = models.CharField(max_length=80, blank=True, default="")

    lecturer_username = models.CharField(max_length=150, blank=True, default="")
    lecturer_full_name = models.CharField(max_length=200, blank=True, default="")

    subject_code = models.CharField(max_length=50, blank=True, default="")
    subject_name = models.CharField(max_length=200, blank=True, default="")
    class_code = models.CharField(max_length=50, blank=True, default="")
    class_name = models.CharField(max_length=200, blank=True, default="")
    subject_type = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["day", "period", "lecturer_username"]

    def __str__(self):
        return f"{self.archive} {self.day} {self.period} {self.subject_code}"


class AcademicDayOverride(models.Model):
    """
    Admin-managed override for a date.
    - If is_holiday=True => treat as holiday (non-working)
    - If is_holiday=False => treat as working day (even if normally weekend)
    """

    date = models.DateField(unique=True)
    is_holiday = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date} ({'Holiday' if self.is_holiday else 'Working'})"


class AcademicEvent(models.Model):
    """Admin-added academic events (deadlines, meetings)."""

    date = models.DateField()
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="academic_events_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.date}: {self.title}"


class TeachingDayLog(models.Model):
    """
    Lecturer-controlled daily checklist.
    This is the only mutable diary-like data, by design.
    """

    lecturer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teaching_logs")
    date = models.DateField()
    teaching_done = models.BooleanField(default=False)
    note = models.CharField(max_length=240, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("lecturer", "date")]
        ordering = ["-date"]

    def __str__(self):
        return f"{self.lecturer.username} {self.date} ({'Done' if self.teaching_done else 'Pending'})"
