from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('timetable.urls')),
    path('admin-portal/', include('admin_portal.urls')),
    path('', include('accounts.urls')),
]
