# Generated manually for model changes

import django.db.models.deletion
from django.db import migrations, models


def set_class_codes(apps, schema_editor):
    """Set unique code for existing Class rows (e.g. CLASS_1, CLASS_2)."""
    Class = apps.get_model('timetable', 'Class')
    for i, obj in enumerate(Class.objects.order_by('id'), start=1):
        obj.code = f'CLASS_{obj.id}' if not obj.code else obj.code
        obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0001_initial'),
    ]

    operations = [
        # Class: add code (nullable first, then backfill, then unique)
        migrations.AddField(
            model_name='class',
            name='code',
            field=models.CharField(max_length=20, null=True, unique=False, blank=True),
        ),
        migrations.RunPython(set_class_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='class',
            name='code',
            field=models.CharField(max_length=20, unique=True),
        ),
        # Subject: add class_assigned FK (nullable for existing rows)
        migrations.AddField(
            model_name='subject',
            name='class_assigned',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='timetable.class'),
        ),
        # TimetableSlot: add time_slot, make day/hour nullable, remove unique_together
        migrations.AddField(
            model_name='timetableslot',
            name='time_slot',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='timetableslot',
            name='day',
            field=models.CharField(blank=True, choices=[('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'), ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday')], max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='timetableslot',
            name='hour',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='timetableslot',
            unique_together=set(),
        ),
    ]
