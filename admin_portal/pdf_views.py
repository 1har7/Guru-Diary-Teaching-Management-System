"""
PDF export for the *live* timetable.

We generate two PDFs and return them as a ZIP:
- lecturer-wise timetable
- class-wise timetable
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from core.pdf_utils import zip_timetable_pdfs
from timetable.models import TimetableSlot
from core.models import ArchivedTimetableSlot, SemesterArchive


@login_required(login_url="admin_portal:login")
def download_timetable_pdfs(request):
    if getattr(request.user, "role", None) != "admin":
        return HttpResponse("Forbidden", status=403)

    slots = TimetableSlot.objects.select_related("lecturer", "subject", "class_assigned").filter(
        day__isnull=False, hour__isnull=False
    )
    rows = []
    for s in slots:
        rows.append(
            {
                "day": s.day,
                "period": s.hour,
                "lecturer": getattr(s.lecturer, "username", "") or "",
                "subject_code": getattr(s.subject, "code", "") or "",
                "subject_name": getattr(s.subject, "name", "") or "",
                "class_name": getattr(s.class_assigned, "name", "") if s.class_assigned else "",
            }
        )

    zip_name, zip_bytes = zip_timetable_pdfs(rows, zip_name="guru_diary_timetables.zip")
    resp = HttpResponse(zip_bytes, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return resp


@login_required(login_url="admin_portal:login")
def download_archive_timetable_pdfs(request, archive_id: int):
    """Admin-only download of archived timetable PDFs as ZIP."""
    if getattr(request.user, "role", None) != "admin":
        return HttpResponse("Forbidden", status=403)

    try:
        archive = SemesterArchive.objects.get(pk=archive_id)
    except SemesterArchive.DoesNotExist:
        return HttpResponse("Archive not found", status=404)

    slots = ArchivedTimetableSlot.objects.filter(archive=archive).all()
    rows = []
    for s in slots:
        rows.append(
            {
                "day": s.day,
                "period": s.period,
                "lecturer": s.lecturer_username,
                "subject_code": s.subject_code,
                "subject_name": s.subject_name,
                "class_name": s.class_name,
            }
        )

    zip_name, zip_bytes = zip_timetable_pdfs(rows, zip_name=f"guru_diary_archive_{archive_id}.zip")
    resp = HttpResponse(zip_bytes, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return resp
