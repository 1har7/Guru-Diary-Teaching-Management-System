from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTest(TestCase):
    def test_create_lecturer(self):
        u = User.objects.create_user(username='lecturer1', password='testpass', role='lecturer')
        self.assertEqual(u.role, 'lecturer')

    def test_create_admin(self):
        u = User.objects.create_user(username='admin1', password='testpass', role='admin')
        self.assertEqual(u.role, 'admin')

    def test_default_role_is_lecturer(self):
        u = User.objects.create_user(username='u1', password='testpass')
        self.assertEqual(u.role, 'lecturer')
