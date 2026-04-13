from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_redirect),
    path('login/', views.LecturerLoginView.as_view(), name='login'),
    path('logout/', views.LecturerLogoutView.as_view(), name='logout'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.welcome_view, name='dashboard'),
    path('app/', views.app_view, name='app'),
    path('subject-selection/', views.subject_selection_view, name='subject_selection'),
    path('diary/request/', views.create_request_view, name='diary_request'),
    path('settings/profile/', views.update_profile_view, name='settings_profile'),
    path('settings/preferences/', views.update_preferences_view, name='settings_preferences'),
    path('settings/diary/', views.update_diary_preferences_view, name='settings_diary'),
    path('settings/change-password/', views.lecturer_change_password_view, name='settings_change_password'),
    path('records/<int:archive_id>/timetable-pdfs/', views.lecturer_archive_pdfs_view, name='records_timetable_pdfs'),
    path('diary/calendar/', views.lecturer_diary_calendar_view, name='diary_calendar'),
    path('diary/calendar/teaching/', views.lecturer_update_teaching_log_view, name='diary_teaching_update'),
]
