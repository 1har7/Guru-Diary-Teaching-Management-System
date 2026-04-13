from django.shortcuts import render, redirect
import datetime
from django.contrib.auth import authenticate, login, get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError
from django.http import JsonResponse

from timetable.generator import DEFAULT_DAYS, DEFAULT_PERIODS, GenerationConfig, generate_from_selections
from timetable.models import Class, LecturerSelection, Subject, TimetableSlot
from diary.models import DiaryEntry, LecturerRequest
from core.models import SemesterArchive, ArchivedTimetableSlot, SystemSettings, UserPreference
from core.quotes import quote_for_day
from core.calendar_utils import progress_counts, progress_percent
from core.calendar_utils import build_override_map, iter_dates, working_day_status
from core.models import AcademicDayOverride, AcademicEvent

User = get_user_model()


@require_http_methods(['GET', 'POST'])
def admin_login_view(request):
    """Dedicated admin login page. Redirects to admin portal or lecturer site by role."""
    if request.user.is_authenticated:
        if getattr(request.user, 'role', None) == 'admin':
            return redirect('admin_portal:dashboard')
        return redirect('dashboard')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if not username or not password:
            error = 'Please enter username and password.'
        else:
            user = authenticate(request, username=username, password=password)
            if user is None:
                error = 'Invalid username or password.'
            elif getattr(user, 'role', None) != 'admin':
                error = 'This page is for administrators only. Use the lecturer login if you are a lecturer.'
            else:
                login(request, user)
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('admin_portal:dashboard')

    return render(request, 'admin_portal/login.html', {
        'error': error,
        'signup_available': not User.objects.filter(role='admin').exists(),
    })


@require_http_methods(['GET', 'POST'])
def admin_signup_view(request):
    """Create the first admin account (only when no admin exists yet)."""
    if request.user.is_authenticated and getattr(request.user, 'role', None) == 'admin':
        return redirect('admin_portal:dashboard')

    admin_exists = User.objects.filter(role='admin').exists()
    if admin_exists and request.method == 'GET':
        return redirect('admin_portal:login')

    errors = []
    if request.method == 'POST':
        if admin_exists:
            return redirect('admin_portal:login')
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        if not username:
            errors.append('Username is required.')
        if User.objects.filter(username=username).exists():
            errors.append('This username is already taken.')
        if not email:
            errors.append('Email is required.')
        if not password1:
            errors.append('Password is required.')
        elif len(password1) < 8:
            errors.append('Password must be at least 8 characters.')
        if password1 != password2:
            errors.append('Passwords do not match.')
        if not errors:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                role='admin',
            )
            login(request, user)
            return redirect('admin_portal:dashboard')

    return render(request, 'admin_portal/signup.html', {
        'errors': errors,
        'signup_available': not admin_exists,
    })


@login_required(login_url='admin_portal:login')
def welcome_view(request):
    """Admin welcome / dashboard page (landing after login)."""
    if getattr(request.user, 'role', None) != 'admin':
        return redirect('dashboard')

    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    settings_obj = SystemSettings.get_solo()

    today = datetime.date.today()
    quote = quote_for_day(today)
    counts = progress_counts(settings_obj, today)
    percent = progress_percent(settings_obj, today)

    lecturer_count = User.objects.filter(role='lecturer').count()
    class_count = Class.objects.count()
    subject_count = Subject.objects.count()
    selection_count = LecturerSelection.objects.count()
    slot_count = TimetableSlot.objects.count()

    return render(request, 'admin_portal/welcome.html', {
        'prefs': prefs,
        'settings': settings_obj,
        'daily_quote': quote,
        'progress': {'percent': percent, 'counts': counts},
        'stats': {
            'lecturers': lecturer_count,
            'classes': class_count,
            'subjects': subject_count,
            'selections': selection_count,
            'slots': slot_count,
        },
    })


@login_required(login_url='admin_portal:login')
def app_view(request):
    """Admin portal workspace (tabs: Timetable/Diary/Records/Settings)."""
    if getattr(request.user, 'role', None) != 'admin':
        return redirect('dashboard')

    prefs, _ = UserPreference.objects.get_or_create(user=request.user)

    lecturer_count = User.objects.filter(role='lecturer').count()
    class_count = Class.objects.count()
    subject_count = Subject.objects.count()
    selection_count = LecturerSelection.objects.count()
    slot_count = TimetableSlot.objects.count()

    system_entries = DiaryEntry.objects.filter(actor='system').order_by('-created_at')[:50]
    announcements = DiaryEntry.objects.filter(entry_type='announcement').order_by('-created_at')[:50]
    requests = LecturerRequest.objects.select_related('lecturer').order_by('-created_at')[:100]
    settings_obj = SystemSettings.get_solo()
    archives = SemesterArchive.objects.all()[:50]

    today = datetime.date.today()
    counts = progress_counts(settings_obj, today)
    percent = progress_percent(settings_obj, today)

    return render(request, 'admin_portal/dashboard.html', {
        'prefs': prefs,
        'stats': {
            'lecturers': lecturer_count,
            'classes': class_count,
            'subjects': subject_count,
            'selections': selection_count,
            'slots': slot_count,
        },
        'diary': {
            'system_entries': system_entries,
            'announcements': announcements,
            'requests': requests,
        },
        'settings': settings_obj,
        'progress': {'percent': percent, 'counts': counts},
        'records': {'archives': archives},
    })


class AdminLogoutView(LogoutView):
    next_page = 'admin_portal:login'


@login_required(login_url='admin_portal:login')
def publish_class_view(request):
    """Publish a new class with optional section."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    try:
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        year = request.POST.get('year')
        semester = request.POST.get('semester')
        section = request.POST.get('section', '').strip() or None

        if not all([name, code, year, semester]):
            return JsonResponse({'error': 'All fields except section are required.'}, status=400)

        year = int(year)
        semester = int(semester)

        # Create the class
        class_obj = Class.objects.create(
            name=name,
            code=code,
            year=year,
            semester=semester,
            section=section
        )

        return JsonResponse({
            'id': class_obj.id,
            'name': str(class_obj),
            'code': class_obj.code,
            'section': class_obj.section
        }, status=201)

    except IntegrityError:
        return JsonResponse({'error': 'Class code already exists.'}, status=400)
    except ValueError:
        return JsonResponse({'error': 'Invalid year or semester value.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='admin_portal:login')
def publish_subject_view(request):
    """Publish a new subject."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    try:
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        class_code = request.POST.get('class_code', '').strip()
        elective_type = request.POST.get('elective_type', 'theory')

        if not all([name, code, class_code]):
            return JsonResponse({'error': 'Name, code, and class code are required.'}, status=400)

        try:
            class_assigned = Class.objects.get(code=class_code)
        except Class.DoesNotExist:
            return JsonResponse({'error': 'Invalid class code.'}, status=400)

        subject = Subject.objects.create(
            name=name,
            code=code,
            class_assigned=class_assigned,
            subject_type=elective_type
        )

        return JsonResponse({
            'id': subject.id,
            'name': subject.name,
            'code': subject.code,
            'class_name': class_assigned.name,
            'subject_type': subject.get_subject_type_display()
        }, status=201)

    except IntegrityError:
        return JsonResponse({'error': 'Subject code already exists.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='admin_portal:login')
def subjects_api_view(request):
    """Get all subjects."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    subjects = Subject.objects.select_related('class_assigned').all()
    data = []
    for subject in subjects:
        data.append({
            'id': subject.id,
            'name': subject.name,
            'code': subject.code,
            'class_name': subject.class_assigned.name if subject.class_assigned else '',
            'subject_type': subject.get_subject_type_display()
        })
    return JsonResponse(data, safe=False)


@login_required(login_url='admin_portal:login')
def delete_subject_view(request, subject_id):
    """Delete a subject."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE method required.'}, status=405)

    try:
        subject = Subject.objects.get(pk=subject_id)
        subject.delete()
        return JsonResponse({'message': 'Subject deleted successfully.'})
    except Subject.DoesNotExist:
        return JsonResponse({'error': 'Subject not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='admin_portal:login')
def classes_api_view(request):
    """Get all classes."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    classes = Class.objects.all()
    data = []
    for cls in classes:
        data.append({
            'id': cls.id,
            'name': str(cls),
            'code': cls.code,
            'year': cls.year,
            'semester': cls.semester,
            'section': cls.section or '—'
        })
    return JsonResponse(data, safe=False)


@login_required(login_url='admin_portal:login')
def delete_class_view(request, class_id):
    """Delete a class."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE method required.'}, status=405)

    try:
        cls = Class.objects.get(pk=class_id)
        cls.delete()
        return JsonResponse({'message': 'Class deleted successfully.'})
    except Class.DoesNotExist:
        return JsonResponse({'error': 'Class not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='admin_portal:login')
def generate_timetable_view(request):
    """Generate timetable."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    try:
        settings_obj = SystemSettings.get_solo()
        # Accept either JSON body or form POST.
        payload = {}
        ctype = request.META.get('CONTENT_TYPE', '') or ''
        if 'application/json' in ctype:
            import json
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                payload = {}
        else:
            payload = request.POST.dict()

        include_saturday = payload.get('include_saturday', settings_obj.working_days != 'mon-fri')
        lab_double = payload.get('lab_double_period', settings_obj.lab_duration_periods == 2)
        clear_existing = payload.get('clear_existing', settings_obj.clear_existing_before_regen)

        # Normalize bool-ish values coming from HTML forms ("on"/"true"/etc).
        def _to_bool(v, default=True):
            if v is None:
                return default
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s in ('1', 'true', 'yes', 'on'):
                return True
            if s in ('0', 'false', 'no', 'off'):
                return False
            return default

        include_saturday = _to_bool(include_saturday, True)
        lab_double = _to_bool(lab_double, True)
        clear_existing = _to_bool(clear_existing, True)

        days = list(DEFAULT_DAYS) if include_saturday else list(DEFAULT_DAYS[:5])
        cfg = GenerationConfig(
            days=days,
            periods=DEFAULT_PERIODS,
            lab_double_period=lab_double,
            clear_existing=clear_existing,
            enable_diary_logging=settings_obj.enable_diary_auto_logging,
        )

        selections = LecturerSelection.objects.select_related('lecturer', 'subject', 'class_assigned').all()
        if not selections.exists():
            return JsonResponse({'error': 'No lecturer selections found. Ask lecturers to select subjects first.'}, status=400)

        had_existing_slots = TimetableSlot.objects.exists()

        if settings_obj.enable_diary_auto_logging:
            DiaryEntry.objects.create(
                actor='system',
                entry_type='timetable_generation_started',
                audience='both',
                title='Timetable generation started',
                is_important=True,
                message=f"Started by admin '{request.user.username}'.",
            )

        summary = generate_from_selections(selections, config=cfg)

        # Distinguish "regenerated" vs "updated" vs "completed" with best-effort heuristics.
        entry_type = 'timetable_generation_completed'
        if clear_existing:
            entry_type = 'timetable_regenerated' if had_existing_slots else 'timetable_generation_completed'
        else:
            entry_type = 'timetable_updated'

        if settings_obj.enable_diary_auto_logging:
            DiaryEntry.objects.create(
                actor='system',
                entry_type=entry_type,
                audience='both',
                title='Timetable generation completed',
                is_important=True,
                message=f"Created slots: {summary.created_slots}. Skipped selections: {summary.skipped_selections}.",
            )
        return JsonResponse({
            'message': 'Timetable generated successfully.',
            'created_slots': summary.created_slots,
            'skipped_selections': summary.skipped_selections,
            'reasons': summary.reasons,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='admin_portal:login')
def post_announcement_view(request):
    """Admin posts an announcement (visible to all lecturers)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    title = request.POST.get('title', '').strip()
    message = request.POST.get('message', '').strip()
    if not title and not message:
        return JsonResponse({'error': 'Please enter a title or message.'}, status=400)

    DiaryEntry.objects.create(
        actor='admin',
        entry_type='announcement',
        audience='lecturers',
        title=title or 'Announcement',
        message=message,
        is_important=True,
    )
    return JsonResponse({'message': 'Announcement posted.'}, status=201)


@login_required(login_url='admin_portal:login')
def request_seen_view(request, request_id):
    """Mark a lecturer request as seen."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    from django.utils import timezone
    try:
        req = LecturerRequest.objects.get(pk=request_id)
        if req.status == 'open':
            req.status = 'seen'
            req.seen_at = timezone.now()
            req.save(update_fields=['status', 'seen_at', 'updated_at'])
        return JsonResponse({'message': 'Marked as seen.', 'status': req.status})
    except LecturerRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found.'}, status=404)


@login_required(login_url='admin_portal:login')
def reply_request_view(request, request_id):
    """Reply once to a lecturer request."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    reply = request.POST.get('reply', '').strip()
    if not reply:
        return JsonResponse({'error': 'Reply cannot be empty.'}, status=400)

    from django.utils import timezone
    try:
        req = LecturerRequest.objects.select_related('lecturer').get(pk=request_id)
        if req.admin_reply:
            return JsonResponse({'error': 'This request already has a reply.'}, status=400)
        req.admin_reply = reply
        req.admin_replied_at = timezone.now()
        req.admin_replied_by = request.user
        if req.status == 'open':
            req.status = 'seen'
            req.seen_at = req.seen_at or timezone.now()
        req.save()

        return JsonResponse({'message': 'Reply saved.', 'status': req.status})
    except LecturerRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found.'}, status=404)


@login_required(login_url='admin_portal:login')
def resolve_request_view(request, request_id):
    """Mark a lecturer request as resolved."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    from django.utils import timezone
    try:
        req = LecturerRequest.objects.get(pk=request_id)
        if req.status != 'resolved':
            req.status = 'resolved'
            req.resolved_at = timezone.now()
            req.save(update_fields=['status', 'resolved_at', 'updated_at'])
        return JsonResponse({'message': 'Marked as resolved.', 'status': req.status})
    except LecturerRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found.'}, status=404)


@login_required(login_url='admin_portal:login')
def admin_diary_calendar_view(request):
    """Admin calendar data for Diary tab (month view)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'GET':
        return JsonResponse({'error': 'GET method required.'}, status=405)

    s = SystemSettings.get_solo()
    year = int(request.GET.get('year') or datetime.date.today().year)
    month = int(request.GET.get('month') or datetime.date.today().month)
    first = datetime.date(year, month, 1)
    if month == 12:
        last = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    dates = list(iter_dates(first, last))
    override_map = build_override_map(dates)

    overrides = AcademicDayOverride.objects.filter(date__gte=first, date__lte=last)
    override_note = {o.date.isoformat(): o.note for o in overrides}

    events = AcademicEvent.objects.filter(date__gte=first, date__lte=last).order_by('date', 'created_at')
    events_by_date = {}
    for e in events:
        events_by_date.setdefault(e.date.isoformat(), []).append({'id': e.id, 'title': e.title, 'message': e.message})

    days = []
    for d in dates:
        is_working, is_holiday = working_day_status(d, s, override_map=override_map)
        days.append({
            'date': d.isoformat(),
            'weekday': d.weekday(),
            'is_working_day': is_working,
            'is_holiday': is_holiday,
            'note': override_note.get(d.isoformat(), ''),
            'events': events_by_date.get(d.isoformat(), []),
        })

    return JsonResponse({'year': year, 'month': month, 'days': days})


@login_required(login_url='admin_portal:login')
def admin_set_day_override_view(request):
    """Admin toggles working day vs holiday for a date (override)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    raw_date = (request.POST.get('date') or '').strip()
    if not raw_date:
        return JsonResponse({'error': 'date is required.'}, status=400)
    try:
        d = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
    except Exception:
        return JsonResponse({'error': 'Invalid date.'}, status=400)

    is_holiday = (request.POST.get('is_holiday') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    note = (request.POST.get('note') or '').strip()[:200]

    obj, _ = AcademicDayOverride.objects.get_or_create(date=d)
    obj.is_holiday = is_holiday
    obj.note = note
    obj.save()
    return JsonResponse({'message': 'Saved.'})


@login_required(login_url='admin_portal:login')
def admin_add_event_view(request):
    """Admin adds an academic event (deadlines, meetings)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    raw_date = (request.POST.get('date') or '').strip()
    title = (request.POST.get('title') or '').strip()
    message = (request.POST.get('message') or '').strip()
    if not raw_date or not title:
        return JsonResponse({'error': 'date and title are required.'}, status=400)

    try:
        d = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
    except Exception:
        return JsonResponse({'error': 'Invalid date.'}, status=400)

    AcademicEvent.objects.create(date=d, title=title[:200], message=message, created_by=request.user)
    return JsonResponse({'message': 'Event added.'}, status=201)


@login_required(login_url='admin_portal:login')
def update_admin_settings_view(request):
    """Update SystemSettings (admin-only)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    s = SystemSettings.get_solo()

    def _to_int(val, default):
        try:
            return int(val)
        except Exception:
            return default

    def _to_bool(val, default):
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        x = str(val).strip().lower()
        if x in ('1', 'true', 'yes', 'on'):
            return True
        if x in ('0', 'false', 'no', 'off'):
            return False
        return default

    # Academic config
    s.academic_year = request.POST.get('academic_year', s.academic_year).strip()
    s.current_semester = _to_int(request.POST.get('current_semester', s.current_semester), s.current_semester)

    # Dates (optional)
    from datetime import datetime
    for field in ('semester_start_date', 'semester_end_date'):
        raw = (request.POST.get(field) or '').strip()
        if raw == '':
            setattr(s, field, None)
            continue
        try:
            setattr(s, field, datetime.strptime(raw, '%Y-%m-%d').date())
        except Exception:
            pass

    # Working rules
    wd = (request.POST.get('working_days') or s.working_days).strip().lower()
    if wd in ('mon-fri', 'mon-sat'):
        s.working_days = wd
    s.periods_per_day = max(1, _to_int(request.POST.get('periods_per_day', s.periods_per_day), s.periods_per_day))
    s.period_duration_minutes = max(1, _to_int(request.POST.get('period_duration_minutes', s.period_duration_minutes), s.period_duration_minutes))
    s.break_period_position = max(0, _to_int(request.POST.get('break_period_position', s.break_period_position), s.break_period_position))

    # Timetable rules
    s.max_hours_per_lecturer_per_week = max(0, _to_int(request.POST.get('max_hours_per_lecturer_per_week', s.max_hours_per_lecturer_per_week), s.max_hours_per_lecturer_per_week))
    s.lab_duration_periods = 2 if _to_int(request.POST.get('lab_duration_periods', s.lab_duration_periods), s.lab_duration_periods) == 2 else 1
    s.allow_consecutive_labs = _to_bool(request.POST.get('allow_consecutive_labs'), s.allow_consecutive_labs)
    s.clear_existing_before_regen = _to_bool(request.POST.get('clear_existing_before_regen'), s.clear_existing_before_regen)

    # System preferences
    s.enable_diary_auto_logging = _to_bool(request.POST.get('enable_diary_auto_logging'), s.enable_diary_auto_logging)
    s.allow_lecturer_requests = _to_bool(request.POST.get('allow_lecturer_requests'), s.allow_lecturer_requests)
    s.admin_email_for_alerts = request.POST.get('admin_email_for_alerts', s.admin_email_for_alerts).strip()

    s.save()
    return JsonResponse({'message': 'Settings saved.'})


@login_required(login_url='admin_portal:login')
def update_admin_preferences_view(request):
    """Per-admin UI preferences (theme)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    theme = (request.POST.get('theme') or '').strip().lower()
    if theme not in ('light', 'dark'):
        return JsonResponse({'error': 'Invalid theme.'}, status=400)

    prefs.theme = theme
    prefs.save(update_fields=['theme', 'updated_at'])
    return JsonResponse({'message': 'Theme saved.'})


@login_required(login_url='admin_portal:login')
def admin_change_password_view(request):
    """Admin change password (admin-only)."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash

    form = PasswordChangeForm(user=request.user, data=request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({'message': 'Password changed successfully.'})

    return JsonResponse({'error': 'Invalid password input.', 'details': form.errors}, status=400)


@login_required(login_url='admin_portal:login')
def archive_current_timetable_view(request):
    """Archive the current (live) timetable into immutable records."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    s = SystemSettings.get_solo()
    academic_year = (request.POST.get('academic_year') or s.academic_year or '').strip() or 'Unknown'
    semester = int(request.POST.get('semester') or s.current_semester or 1)
    note = (request.POST.get('note') or '').strip()

    archive = SemesterArchive.objects.create(
        academic_year=academic_year,
        semester=semester,
        semester_start_date=s.semester_start_date,
        semester_end_date=s.semester_end_date,
        created_by=request.user,
        note=note,
    )

    live_slots = TimetableSlot.objects.select_related('lecturer', 'subject', 'class_assigned').all()
    bulk = []
    for slot in live_slots:
        bulk.append(ArchivedTimetableSlot(
            archive=archive,
            day=slot.day or '',
            period=slot.hour,
            time_slot=slot.time_slot or '',
            lecturer_username=getattr(slot.lecturer, 'username', '') or '',
            lecturer_full_name=f"{getattr(slot.lecturer, 'first_name', '')} {getattr(slot.lecturer, 'last_name', '')}".strip(),
            subject_code=getattr(slot.subject, 'code', '') or '',
            subject_name=getattr(slot.subject, 'name', '') or '',
            subject_type=getattr(slot.subject, 'subject_type', '') or '',
            class_code=getattr(slot.class_assigned, 'code', '') if slot.class_assigned else '',
            class_name=getattr(slot.class_assigned, 'name', '') if slot.class_assigned else '',
        ))
    if bulk:
        ArchivedTimetableSlot.objects.bulk_create(bulk, batch_size=500)

    return JsonResponse({'message': 'Timetable archived.', 'archive_id': archive.id}, status=201)


@login_required(login_url='admin_portal:login')
def timetable_api_view(request):
    """Get timetable data."""
    if getattr(request.user, 'role', None) != 'admin':
        return JsonResponse({'error': 'Admin access required.'}, status=403)

    slots = TimetableSlot.objects.select_related('subject', 'lecturer', 'class_assigned').all()
    data = []
    for slot in slots:
        # Prefer stable identifier for grouping in the UI.
        lecturer_username = getattr(slot.lecturer, 'username', '') or ''
        lecturer_full_name = f"{getattr(slot.lecturer, 'first_name', '')} {getattr(slot.lecturer, 'last_name', '')}".strip()
        data.append({
            'id': slot.id,
            'subject': slot.subject.name,
            'subject_code': slot.subject.code,
            'lecturer': lecturer_username,
            'lecturer_name': lecturer_full_name or lecturer_username,
            'class': slot.class_assigned.name if slot.class_assigned else '',
            'day': slot.day,
            'period': slot.hour,
            'time_slot': slot.time_slot
        })
    return JsonResponse(data, safe=False)
