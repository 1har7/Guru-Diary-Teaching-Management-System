from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from django.conf import settings as django_settings
from django.core.mail import send_mail
from django.db import transaction

from accounts.models import User
from core.calendar_utils import progress_counts, progress_percent
from core.models import SystemSettings, UserPreference
from diary.models import DiaryEntry, LecturerRequest


def academic_key(s: SystemSettings) -> str:
    return f"{s.academic_year or 'unknown'}:sem{s.current_semester}"


def _maybe_email(user: User, entry: DiaryEntry) -> None:
    try:
        prefs = getattr(user, "prefs", None)
        if prefs is None:
            prefs = UserPreference.objects.filter(user=user).first()
        if not prefs or not prefs.diary_email_alerts:
            return
        if not user.email:
            return
        subject = f"Guru Diary: {entry.title or entry.entry_type}"
        body = entry.message or entry.title or entry.entry_type
        # If email backend isn't configured, this will raise; we swallow errors by design.
        send_mail(subject, body, django_settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
    except Exception:
        return


def ensure_progress_reminders_for_lecturer(user: User, *, today: Optional[date] = None) -> None:
    if getattr(user, "role", None) != "lecturer":
        return

    s = SystemSettings.get_solo()
    if not s.enable_diary_auto_logging:
        return

    today = today or date.today()
    p = progress_percent(s, today)
    c = progress_counts(s, today)
    if p is None or c is None:
        return

    key = academic_key(s)

    def exists(entry_type: str) -> bool:
        return DiaryEntry.objects.filter(
            lecturer=user,
            entry_type=entry_type,
            meta__academic_key=key,
        ).exists()

    with transaction.atomic():
        if p >= 50 and not exists("progress_reminder_50"):
            e = DiaryEntry.objects.create(
                actor="system",
                entry_type="progress_reminder_50",
                audience="lecturers",
                lecturer=user,
                title="Progress checkpoint: 50%",
                is_important=True,
                message="Based on working days elapsed, you should be around 50% completion by now.",
                meta={"academic_key": key, "percent": p},
            )
            _maybe_email(user, e)

        if p >= 75 and not exists("progress_reminder_75"):
            e = DiaryEntry.objects.create(
                actor="system",
                entry_type="progress_reminder_75",
                audience="lecturers",
                lecturer=user,
                title="Progress checkpoint: 75%",
                is_important=True,
                message="Based on working days elapsed, you should be around 75% completion by now.",
                meta={"academic_key": key, "percent": p},
            )
            _maybe_email(user, e)

        # End approaching: within last ~10% of working days, or within 7 calendar days.
        days_left = max(0, c.total_days - c.elapsed_days)
        working_left = max(0, c.total_working_days - c.elapsed_working_days)
        end_soon = days_left <= 7 or (c.total_working_days > 0 and (working_left / c.total_working_days) <= 0.10)
        if end_soon and not exists("progress_reminder_end_soon"):
            e = DiaryEntry.objects.create(
                actor="system",
                entry_type="progress_reminder_end_soon",
                audience="lecturers",
                lecturer=user,
                title="Academic end approaching",
                is_important=True,
                message="The academic end date is approaching. Consider reviewing pending sessions and assessments.",
                meta={"academic_key": key, "days_left": days_left, "working_days_left": working_left},
            )
            _maybe_email(user, e)


def ensure_weekly_summary_for_lecturer(user: User, *, today: Optional[date] = None) -> None:
    if getattr(user, "role", None) != "lecturer":
        return

    s = SystemSettings.get_solo()
    if not s.enable_diary_auto_logging:
        return

    today = today or date.today()
    iso_year, iso_week, _iso_weekday = today.isocalendar()
    key = academic_key(s)

    already = DiaryEntry.objects.filter(
        lecturer=user,
        entry_type="weekly_summary",
        meta__academic_key=key,
        meta__iso_year=int(iso_year),
        meta__iso_week=int(iso_week),
    ).exists()
    if already:
        return

    # Week range (Mon..Sun) for the current ISO week.
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Working/holiday counts (time-based, same for all lecturers).
    # We'll compute using day overrides and base rules.
    from core.calendar_utils import build_override_map, iter_dates, working_day_status

    dates = list(iter_dates(week_start, week_end))
    override_map = build_override_map(dates)
    working_days = 0
    holidays = 0
    for d in dates:
        is_working, is_holiday = working_day_status(d, s, override_map=override_map)
        working_days += 1 if is_working else 0
        holidays += 1 if is_holiday else 0

    # Teaching done ticks
    from core.models import TeachingDayLog

    done_days = TeachingDayLog.objects.filter(lecturer=user, date__gte=week_start, date__lte=week_end, teaching_done=True).count()

    # Timetable changes (system entries)
    timetable_changes = DiaryEntry.objects.filter(
        audience__in=["lecturers", "both"],
        entry_type__in=["timetable_updated", "timetable_regenerated", "timetable_generation_completed"],
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
    ).count()

    # Requests raised
    req_count = LecturerRequest.objects.filter(lecturer=user, created_at__date__gte=week_start, created_at__date__lte=week_end).count()

    title = f"Weekly summary (Week {iso_week})"
    message = (
        f"Week {iso_week} summary:\n"
        f"- Working days: {working_days}\n"
        f"- Holidays: {holidays}\n"
        f"- Days marked as teaching done: {done_days}\n"
        f"- Timetable changes logged: {timetable_changes}\n"
        f"- Diary requests raised: {req_count}\n"
    )

    DiaryEntry.objects.create(
        actor="system",
        entry_type="weekly_summary",
        audience="lecturers",
        lecturer=user,
        title=title,
        is_important=False,
        message=message,
        meta={"academic_key": key, "iso_year": int(iso_year), "iso_week": int(iso_week)},
    )

