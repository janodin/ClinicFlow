from decimal import Decimal

from django.db import migrations


DEFAULT_NON_MEDICINE_CATEGORIES = [
    ("Primary Care", "primary_care", 0),
    ("Laboratory", "laboratory", 1),
    ("Cancer Screening", "cancer_screening", 3),
]


def normalize_default_non_medicine_limits(apps, schema_editor):
    YakapCoverageCategory = apps.get_model("yakap", "YakapCoverageCategory")
    ClinicYakapSettings = apps.get_model("yakap", "ClinicYakapSettings")
    clinics_with_custom_non_medicine_limit = ClinicYakapSettings.objects.exclude(
        default_non_medicine_limit=Decimal("0.00"),
    ).values("clinic_id")
    for name, category_type, sort_order in DEFAULT_NON_MEDICINE_CATEGORIES:
        YakapCoverageCategory.objects.filter(
            name=name,
            category_type=category_type,
            sort_order=sort_order,
            is_active=True,
            notes="",
            annual_limit=Decimal("20000.00"),
        ).exclude(clinic_id__in=clinics_with_custom_non_medicine_limit).update(annual_limit=Decimal("0.00"))


class Migration(migrations.Migration):
    dependencies = [
        ("yakap", "0002_appointmentyakapsnapshot_estimated_covered_amount_at_booking_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_default_non_medicine_limits, migrations.RunPython.noop),
    ]
