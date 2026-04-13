from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .models import AcademicDayOverride, SystemSettings


@dataclass(frozen=True)
class WorkingDayCounts:
    total_working_days: int
    elapsed_working_days: int
    total_days: int
    elapsed_days: int


def iter_dates(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d = d + timedelta(days=1)


def is_weekend(d: date) -> bool:
    # Monday=0 ... Sunday=6
    return d.weekday() >= 5


def is_working_day_base(d: date, settings: SystemSettings) -> bool:
    # Sunday is always non-working unless explicitly overridden to working.
    if d.weekday() == 6:
        return False
    if settings.working_days == "mon-fri":
        return d.weekday() < 5
    return d.weekday() < 6  # mon-sat


def working_day_status(
    d: date,
    settings: SystemSettings,
    *,
    override_map: Optional[Dict[date, bool]] = None,
) -> Tuple[bool, bool]:
    """
    Returns (is_working_day, is_holiday).
    If an override exists for d:
      - override True => holiday
      - override False => working
    """
    if override_map is not None and d in override_map:
        is_holiday = bool(override_map[d])
        return (not is_holiday, is_holiday)

    base_working = is_working_day_base(d, settings)
    return (base_working, not base_working)


def build_override_map(dates: List[date]) -> Dict[date, bool]:
    qs = AcademicDayOverride.objects.filter(date__in=dates).values("date", "is_holiday")
    return {row["date"]: bool(row["is_holiday"]) for row in qs}


def progress_counts(settings: SystemSettings, today: date) -> Optional[WorkingDayCounts]:
    if not settings.semester_start_date or not settings.semester_end_date:
        return None
    start = settings.semester_start_date
    end = settings.semester_end_date
    if end < start:
        return None

    total_days = (end - start).days + 1
    elapsed_days = 0
    if today < start:
        elapsed_days = 0
    elif today > end:
        elapsed_days = total_days
    else:
        elapsed_days = (today - start).days + 1

    date_list = list(iter_dates(start, end))
    override_map = build_override_map(date_list)

    total_working = 0
    elapsed_working = 0
    for d in date_list:
        is_working, _is_holiday = working_day_status(d, settings, override_map=override_map)
        if is_working:
            total_working += 1
            if d <= today:
                elapsed_working += 1

    return WorkingDayCounts(
        total_working_days=total_working,
        elapsed_working_days=elapsed_working,
        total_days=total_days,
        elapsed_days=elapsed_days,
    )


def progress_percent(settings: SystemSettings, today: date) -> Optional[float]:
    c = progress_counts(settings, today)
    if c is None or c.total_working_days <= 0:
        return None
    return round((c.elapsed_working_days / c.total_working_days) * 100.0, 2)

