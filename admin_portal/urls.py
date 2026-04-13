from django.urls import path
from . import views
from . import pdf_views

app_name = 'admin_portal'

urlpatterns = [
    path('login/', views.admin_login_view, name='login'),
    path('logout/', views.AdminLogoutView.as_view(), name='logout'),
    path('signup/', views.admin_signup_view, name='signup'),
    path('publish-class/', views.publish_class_view, name='publish_class'),
    path('api/diary/announcement/', views.post_announcement_view, name='diary_announcement'),
    path('api/diary/calendar/', views.admin_diary_calendar_view, name='diary_calendar'),
    path('api/diary/calendar/day/', views.admin_set_day_override_view, name='diary_calendar_day'),
    path('api/diary/calendar/event/', views.admin_add_event_view, name='diary_calendar_event'),
    path('api/diary/requests/<int:request_id>/seen/', views.request_seen_view, name='diary_request_seen'),
    path('api/diary/requests/<int:request_id>/reply/', views.reply_request_view, name='diary_request_reply'),
    path('api/diary/requests/<int:request_id>/resolve/', views.resolve_request_view, name='diary_request_resolve'),
    path('api/publish-subject/', views.publish_subject_view, name='publish_subject'),
    path('api/subjects/', views.subjects_api_view, name='subjects_api'),
    path('api/subjects/<int:subject_id>/delete/', views.delete_subject_view, name='delete_subject'),
    path('api/classes/', views.classes_api_view, name='classes_api'),
    path('api/classes/<int:class_id>/delete/', views.delete_class_view, name='delete_class'),
    path('api/generate-timetable/', views.generate_timetable_view, name='generate_timetable'),
    path('api/timetable/', views.timetable_api_view, name='timetable_api'),
    path('timetable-pdfs/', pdf_views.download_timetable_pdfs, name='timetable_pdfs'),
    path('records/<int:archive_id>/timetable-pdfs/', pdf_views.download_archive_timetable_pdfs, name='records_timetable_pdfs'),
    path('api/records/archive/', views.archive_current_timetable_view, name='records_archive'),
    path('api/settings/', views.update_admin_settings_view, name='admin_settings_update'),
    path('api/settings/change-password/', views.admin_change_password_view, name='admin_change_password'),
    path('api/preferences/', views.update_admin_preferences_view, name='admin_preferences_update'),
    path('app/', views.app_view, name='app'),
    path('', views.welcome_view, name='dashboard'),
]
