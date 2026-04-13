from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from django.db import transaction

from .models import LecturerSelection, TimetableSlot
from diary.models import DiaryEntry


@dataclass(frozen=True)
class GenerationConfig:
    days: Sequence[str]
    periods: Sequence[int]
    lab_double_period: bool = True
    clear_existing: bool = True
    enable_diary_logging: bool = True


@dataclass(frozen=True)
class GenerationSummary:
    created_slots: int
    skipped_selections: int
    reasons: dict


DEFAULT_DAYS: List[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
DEFAULT_PERIODS: List[int] = [1, 2, 3, 4, 5, 6]
PERIOD_TIMES = {
    1: "9:50-10:50",
    2: "10:50-11:50",
    3: "12:00-1:00",
    4: "1:00-2:00",
    5: "2:30-3:30",
    6: "3:30-4:30",
}


def _slot_display(day: str, period: int) -> str:
    suffix = "th"
    if period == 1:
        suffix = "st"
    elif period == 2:
        suffix = "nd"
    elif period == 3:
        suffix = "rd"
    return f"{day} {period}{suffix} ({PERIOD_TIMES.get(period, '')})".strip()


def _iter_all_slots(days: Sequence[str], periods: Sequence[int]) -> List[Tuple[str, int]]:
    all_slots: List[Tuple[str, int]] = []
    for d in days:
        for p in periods:
            all_slots.append((d, int(p)))
    return all_slots


def generate_from_selections(
    selections: Iterable[LecturerSelection],
    *,
    config: Optional[GenerationConfig] = None,
) -> GenerationSummary:
    """
    Generate TimetableSlot rows from LecturerSelection rows.

    Constraints enforced:
    - A lecturer cannot be assigned to two classes in the same (day, period).
    - A class cannot have two subjects in the same (day, period).

    Optional refinement:
    - If lab_double_period=True and subject.subject_type == 'lab', allocate two consecutive periods on the same day.
    """
    cfg = config or GenerationConfig(days=DEFAULT_DAYS, periods=DEFAULT_PERIODS)
    all_slots = _iter_all_slots(cfg.days, cfg.periods)

    # Track busy slots
    lecturer_busy: dict[int, set[Tuple[str, int]]] = {}
    class_busy: dict[int, set[Tuple[str, int]]] = {}

    def is_free(lecturer_id: int, class_id: int, day: str, period: int) -> bool:
        if (day, period) in lecturer_busy.get(lecturer_id, set()):
            return False
        if (day, period) in class_busy.get(class_id, set()):
            return False
        return True

    def mark_busy(lecturer_id: int, class_id: int, day: str, period: int) -> None:
        lecturer_busy.setdefault(lecturer_id, set()).add((day, period))
        class_busy.setdefault(class_id, set()).add((day, period))

    # Group selections by class so we don't create class clashes.
    by_class: dict[int, list[LecturerSelection]] = {}
    for s in selections:
        # LecturerSelection.class_assigned should always exist; be defensive anyway.
        cls_id = s.class_assigned_id
        if not cls_id:
            continue
        by_class.setdefault(int(cls_id), []).append(s)

    created = 0
    skipped = 0
    reasons: dict[str, int] = {"no_free_slot": 0, "no_free_double_slot": 0}

    with transaction.atomic():
        if cfg.clear_existing:
            TimetableSlot.objects.all().delete()

        # Stable ordering: class_id then selection PK so generation is deterministic-ish.
        for cls_id in sorted(by_class.keys()):
            # Sort selections per class by subject code then lecturer username to keep output stable.
            class_selections = by_class[cls_id]
            class_selections.sort(key=lambda s: (getattr(s.subject, "code", ""), getattr(s.lecturer, "username", ""), s.pk))

            for sel in class_selections:
                lecturer_id = sel.lecturer_id
                class_id = sel.class_assigned_id
                if not lecturer_id or not class_id:
                    skipped += 1
                    continue

                is_lab = cfg.lab_double_period and getattr(sel.subject, "subject_type", "") == "lab"

                if is_lab:
                    # Find (day, p) and (day, p+1) both free
                    found: Optional[Tuple[str, int]] = None
                    for day, period in all_slots:
                        if (period + 1) not in cfg.periods:
                            continue
                        if is_free(lecturer_id, class_id, day, period) and is_free(lecturer_id, class_id, day, period + 1):
                            found = (day, period)
                            break
                    if not found:
                        skipped += 1
                        reasons["no_free_double_slot"] += 1
                        if cfg.enable_diary_logging:
                            DiaryEntry.objects.create(
                                actor="system",
                                entry_type="subject_rejected",
                                audience="lecturers",
                                lecturer=sel.lecturer,
                                title="Subject rejected",
                                is_important=True,
                                message=(
                                    f"Could not schedule lab '{sel.subject.code} - {sel.subject.name}' for "
                                    f"{sel.class_assigned.code} due to lack of a free double period."
                                ),
                            )
                            DiaryEntry.objects.create(
                                actor="system",
                                entry_type="clash_detected",
                                audience="lecturers",
                                lecturer=sel.lecturer,
                                title="Timetable clash detected",
                                is_important=True,
                                message="A clash-free slot could not be found for one of your selections.",
                            )
                        continue
                    day, period = found
                    for p in (period, period + 1):
                        TimetableSlot.objects.create(
                            lecturer=sel.lecturer,
                            subject=sel.subject,
                            class_assigned=sel.class_assigned,
                            day=day,
                            hour=p,
                            time_slot=_slot_display(day, p),
                        )
                        mark_busy(lecturer_id, class_id, day, p)
                        created += 1
                    if cfg.enable_diary_logging:
                        DiaryEntry.objects.create(
                            actor="system",
                            entry_type="subject_assigned",
                            audience="lecturers",
                            lecturer=sel.lecturer,
                            title="Subject assigned",
                            is_important=True,
                            message=(
                                f"Assigned lab '{sel.subject.code} - {sel.subject.name}' for {sel.class_assigned.code} "
                                f"on {day} periods {period} & {period + 1}."
                            ),
                        )
                else:
                    found2: Optional[Tuple[str, int]] = None
                    for day, period in all_slots:
                        if is_free(lecturer_id, class_id, day, period):
                            found2 = (day, period)
                            break
                    if not found2:
                        skipped += 1
                        reasons["no_free_slot"] += 1
                        if cfg.enable_diary_logging:
                            DiaryEntry.objects.create(
                                actor="system",
                                entry_type="subject_rejected",
                                audience="lecturers",
                                lecturer=sel.lecturer,
                                title="Subject rejected",
                                is_important=True,
                                message=(
                                    f"Could not schedule '{sel.subject.code} - {sel.subject.name}' for "
                                    f"{sel.class_assigned.code} due to lack of a free slot."
                                ),
                            )
                            DiaryEntry.objects.create(
                                actor="system",
                                entry_type="clash_detected",
                                audience="lecturers",
                                lecturer=sel.lecturer,
                                title="Timetable clash detected",
                                is_important=True,
                                message="A clash-free slot could not be found for one of your selections.",
                            )
                        continue
                    day, period = found2
                    TimetableSlot.objects.create(
                        lecturer=sel.lecturer,
                        subject=sel.subject,
                        class_assigned=sel.class_assigned,
                        day=day,
                        hour=period,
                        time_slot=_slot_display(day, period),
                    )
                    mark_busy(lecturer_id, class_id, day, period)
                    created += 1
                    if cfg.enable_diary_logging:
                        DiaryEntry.objects.create(
                            actor="system",
                            entry_type="subject_assigned",
                            audience="lecturers",
                            lecturer=sel.lecturer,
                            title="Subject assigned",
                            is_important=True,
                            message=(
                                f"Assigned '{sel.subject.code} - {sel.subject.name}' for {sel.class_assigned.code} "
                                f"on {day} period {period}."
                            ),
                        )

    return GenerationSummary(created_slots=created, skipped_selections=skipped, reasons=reasons)
