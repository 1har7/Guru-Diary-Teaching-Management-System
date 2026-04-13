from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('lecturer', 'Lecturer'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='lecturer')

    # Lecturer profile fields (used by Settings tab). Optional so existing DB rows migrate cleanly.
    phone_number = models.CharField(max_length=30, blank=True, default="")
    employee_id = models.CharField(max_length=50, blank=True, default="")
    department = models.CharField(max_length=120, blank=True, default="")
