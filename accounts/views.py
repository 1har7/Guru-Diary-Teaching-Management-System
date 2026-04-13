import json
import datetime
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q

from .models import User
from diary.models import DiaryEntry, LecturerRequest
from core.models import SystemSettings, UserPreference, SemesterArchive, ArchivedTimetableSlot
from core.pdf_utils import zip_timetable_pdfs
from core.quotes import quote_for_day
from core.calendar_utils import progress_counts, progress_percent
from core.calendar_utils import build_override_map, iter_dates, working_day_status
from core.models import AcademicEvent, TeachingDayLog
from diary.services import ensure_progress_reminders_for_lecturer, ensure_weekly_summary_for_lecturer
from timetable.models import Subject, LecturerSelection, TimetableSlot


def home_redirect(request):
    """Root URL: admins -> admin portal, lecturers -> dashboard, else login."""
    if not request.user.is_authenticated:
        return redirect('login')
    role = getattr(request.user, 'role', None)
    if role == 'admin':
        return redirect('admin_portal:dashboard')
    if role == 'lecturer':
        return redirect('dashboard')
    return redirect('login')


def register_view(request):
    """Lecturer registration."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method != 'POST':
        return render(request, 'accounts/register.html', {'form': None})
    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    password1 = request.POST.get('password1', '')
    password2 = request.POST.get('password2', '')
    errors = []
    if not username:
        errors.append('Username is required.')
    if User.objects.filter(username=username).exists():
        errors.append('Username already exists.')
    if not email:
        errors.append('Email is required.')
    if not password1:
        errors.append('Password is required.')
    if password1 != password2:
        errors.append('Passwords do not match.')
    if len(password1) < 8:
        errors.append('Password must be at least 8 characters.')
    if errors:
        return render(request, 'accounts/register.html', {'errors': errors})
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password1,
        first_name=first_name,
        last_name=last_name,
        role='lecturer',
    )
    login(request, user)
    return redirect('dashboard')


class LecturerLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        """After login: use ?next= if set, else admin portal for admins, lecturer dashboard for lecturers."""
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        role = getattr(self.request.user, 'role', None)
        if role == 'admin':
            return reverse('admin_portal:dashboard')
        return reverse('dashboard')


class LecturerLogoutView(LogoutView):
    next_page = 'login'


@login_required(login_url='login')
def welcome_view(request):
    """Lecturer welcome / dashboard page (landing after login)."""
    if request.user.role != 'lecturer':
        return redirect('login')

    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    today = datetime.date.today()
    quote = quote_for_day(today)
    system_settings = SystemSettings.get_solo()
    percent = progress_percent(system_settings, today)
    counts = progress_counts(system_settings, today)

    return render(request, 'accounts/welcome.html', {
        'prefs': prefs,
        'daily_quote': quote,
        'progress': {'percent': percent, 'counts': counts},
    })


def app_view(request):
    """Lecturer app workspace (tabs: Timetable/Diary/Records/Settings)."""
    if request.user.role != 'lecturer':
        return redirect('login')
    available_subjects = Subject.objects.select_related('class_assigned').filter(class_assigned__isnull=False)
    user_selections = LecturerSelection.objects.filter(lecturer=request.user).select_related('subject', 'subject__class_assigned')
    timetable_slots = TimetableSlot.objects.filter(lecturer=request.user).select_related('subject', 'subject__class_assigned')
    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    system_settings = SystemSettings.get_solo()

    # Diary auto entries (advisory). Runs lazily on page load.
    ensure_progress_reminders_for_lecturer(request.user)
    ensure_weekly_summary_for_lecturer(request.user)

    # Prepare timetable data for grid view
    timetable_data = []
    for slot in timetable_slots:
        if slot.day and slot.hour:
            timetable_data.append({
                'day': slot.day,
                'period': slot.hour,
                'subject': slot.subject.name,
                'subject_code': slot.subject.code,
                'class': slot.class_assigned.name if slot.class_assigned else '',
                'time_slot': slot.time_slot or f"{slot.day} {slot.hour}",
            })

    # Diary entries: optionally filter to important only.
    diary_entries_qs = DiaryEntry.objects.filter(audience__in=['lecturers', 'both']).filter(
        Q(lecturer__isnull=True) | Q(lecturer=request.user)
    ).order_by('-created_at')
    if prefs.diary_only_important:
        diary_entries_qs = diary_entries_qs.filter(is_important=True)

    archives = SemesterArchive.objects.all()[:50]
    closed_requests = LecturerRequest.objects.filter(lecturer=request.user, status='resolved').order_by('-created_at')[:50]
    past_subjects = ArchivedTimetableSlot.objects.filter(lecturer_username=request.user.username).values(
        'subject_code', 'subject_name'
    ).distinct()[:100]

    return render(request, 'accounts/dashboard.html', {
        'available_subjects': available_subjects,
        'user_selections': user_selections,
        'timetable_slots': timetable_slots,
        'timetable_data': json.dumps(timetable_data),
        'stats': {
            'available_subjects': available_subjects.count(),
            'selected_subjects': user_selections.count(),
            'timetable_slots': timetable_slots.count(),
        },
        'diary': {
            'entries': diary_entries_qs[:50],
            'requests': LecturerRequest.objects.filter(lecturer=request.user).order_by('-created_at')[:50],
        },
        'prefs': prefs,
        'system_settings': system_settings,
        'progress': {
            'percent': progress_percent(system_settings, datetime.date.today()),
            'counts': progress_counts(system_settings, datetime.date.today()),
        },
        'records': {
            'archives': archives,
            'closed_requests': closed_requests,
            'past_subjects': list(past_subjects),
        },
    })


@login_required(login_url='login')
def create_request_view(request):
    """Lecturer raises a request to admin. Read-only after submission."""
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    system_settings = SystemSettings.get_solo()
    if not system_settings.allow_lecturer_requests:
        return JsonResponse({'success': False, 'error': 'Requests are currently disabled by admin.'}, status=403)

    req_type = request.POST.get('request_type', '').strip()
    desc = request.POST.get('description', '').strip()
    if not req_type or not desc:
        return JsonResponse({'success': False, 'error': 'Type and description are required.'}, status=400)

    LecturerRequest.objects.create(
        lecturer=request.user,
        request_type=req_type,
        description=desc,
        status='open',
    )

    return JsonResponse({'success': True})


@login_required(login_url='login')
def update_profile_view(request):
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone_number', '').strip()

    # Basic validation
    if email and User.objects.exclude(pk=request.user.pk).filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'This email is already in use.'}, status=400)

    request.user.email = email
    request.user.phone_number = phone
    request.user.save(update_fields=['email', 'phone_number'])
    return JsonResponse({'success': True, 'message': 'Profile updated.'})


@login_required(login_url='login')
def update_preferences_view(request):
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    prefs, _ = UserPreference.objects.get_or_create(user=request.user)
    theme = request.POST.get('theme', prefs.theme)
    timetable_view = request.POST.get('timetable_view', prefs.timetable_view)
    time_format = request.POST.get('time_format', prefs.time_format)

    if theme in ('light', 'dark'):
        prefs.theme = theme
    if timetable_view in ('grid', 'list'):
        prefs.timetable_view = timetable_view
    if time_format in ('12h', '24h'):
        prefs.time_format = time_format
    prefs.save()
    return JsonResponse({'success': True, 'message': 'Preferences saved.'})


@login_required(login_url='login')
def update_diary_preferences_view(request):
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    prefs, _ = UserPreference.objects.get_or_create(user=request.user)

    def _to_bool(v):
        if v is None:
            return False
        x = str(v).strip().lower()
        return x in ('1', 'true', 'yes', 'on')

    prefs.diary_email_alerts = _to_bool(request.POST.get('diary_email_alerts'))
    prefs.diary_only_important = _to_bool(request.POST.get('diary_only_important'))
    prefs.save()
    return JsonResponse({'success': True, 'message': 'Diary preferences saved.'})


@login_required(login_url='login')
def lecturer_change_password_view(request):
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash

    form = PasswordChangeForm(user=request.user, data=request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return JsonResponse({'success': True, 'message': 'Password changed successfully.'})
    return JsonResponse({'success': False, 'error': 'Invalid password input.', 'details': form.errors}, status=400)


@login_required(login_url='login')
def lecturer_archive_pdfs_view(request, archive_id: int):
    """Lecturer downloads archived timetable PDFs as ZIP."""
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)

    try:
        archive = SemesterArchive.objects.get(pk=archive_id)
    except SemesterArchive.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Archive not found.'}, status=404)

    slots = ArchivedTimetableSlot.objects.filter(archive=archive).all()
    rows = []
    for s in slots:
        rows.append({
            "day": s.day,
            "period": s.period,
            "lecturer": s.lecturer_username,
            "subject_code": s.subject_code,
            "subject_name": s.subject_name,
            "class_name": s.class_name,
        })

    zip_name, zip_bytes = zip_timetable_pdfs(rows, zip_name=f"guru_diary_archive_{archive_id}.zip")
    resp = HttpResponse(zip_bytes, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return resp


@login_required(login_url='login')
def lecturer_diary_calendar_view(request):
    """Lecturer calendar view data for Diary tab (month view)."""
    if request.user.role != 'lecturer':
        return JsonResponse({'error': 'Lecturers only.'}, status=403)
    if request.method != 'GET':
        return JsonResponse({'error': 'GET required.'}, status=405)

    s = SystemSettings.get_solo()
    year = int(request.GET.get('year') or datetime.date.today().year)
    month = int(request.GET.get('month') or datetime.date.today().month)
    first = datetime.date(year, month, 1)
    # month end
    if month == 12:
        last = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    dates = list(iter_dates(first, last))
    override_map = build_override_map(dates)

    events = AcademicEvent.objects.filter(date__gte=first, date__lte=last).order_by('date', 'created_at')
    events_by_date = {}
    for e in events:
        events_by_date.setdefault(e.date.isoformat(), []).append({'title': e.title, 'message': e.message})

    logs = TeachingDayLog.objects.filter(lecturer=request.user, date__gte=first, date__lte=last)
    logs_by_date = {l.date.isoformat(): {'done': bool(l.teaching_done), 'note': l.note} for l in logs}

    days = []
    for d in dates:
        is_working, is_holiday = working_day_status(d, s, override_map=override_map)
        log = logs_by_date.get(d.isoformat(), {})
        days.append({
            'date': d.isoformat(),
            'weekday': d.weekday(),
            'is_working_day': is_working,
            'is_holiday': is_holiday,
            'teaching_done': bool(log.get('done', False)),
            'note': log.get('note', ''),
            'events': events_by_date.get(d.isoformat(), []),
        })

    return JsonResponse({
        'year': year,
        'month': month,
        'days': days,
    })


@login_required(login_url='login')
def lecturer_update_teaching_log_view(request):
    """Lecturer marks a day as teaching done + optional note."""
    if request.user.role != 'lecturer':
        return JsonResponse({'error': 'Lecturers only.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    raw_date = (request.POST.get('date') or '').strip()
    if not raw_date:
        return JsonResponse({'error': 'date is required.'}, status=400)

    try:
        d = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
    except Exception:
        return JsonResponse({'error': 'Invalid date.'}, status=400)

    done = (request.POST.get('teaching_done') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    note = (request.POST.get('note') or '').strip()[:240]

    log, _ = TeachingDayLog.objects.get_or_create(lecturer=request.user, date=d)
    log.teaching_done = done
    log.note = note
    log.save()
    return JsonResponse({'message': 'Saved.'})


@login_required(login_url='login')
def subject_selection_view(request):
    """POST: add a subject selection for the current lecturer. DELETE: remove a subject selection."""
    if request.user.role != 'lecturer':
        return JsonResponse({'success': False, 'error': 'Lecturers only.'}, status=403)

    if request.method == 'POST':
        try:
            subject_id = request.POST.get('subject')
            if not subject_id:
                return JsonResponse({'success': False, 'error': 'No subject selected.'})
            subject = Subject.objects.get(pk=subject_id)
            if not subject.class_assigned_id:
                return JsonResponse({'success': False, 'error': 'Invalid subject.'})
            LecturerSelection.objects.get_or_create(
                lecturer=request.user,
                subject=subject,
                class_assigned=subject.class_assigned,
            )
            return JsonResponse({'success': True})
        except Subject.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Subject not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    elif request.method == 'DELETE':
        try:
            import json
            data = json.loads(request.body)
            selection_id = data.get('selection_id')
            if not selection_id:
                return JsonResponse({'success': False, 'error': 'No selection ID provided.'})
            selection = LecturerSelection.objects.get(pk=selection_id, lecturer=request.user)
            selection.delete()
            return JsonResponse({'success': True})
        except LecturerSelection.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Selection not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Method not allowed.'}, status=405)
