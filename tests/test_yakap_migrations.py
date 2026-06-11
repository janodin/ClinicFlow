from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


YAKAP_0002 = "0002_appointmentyakapsnapshot_estimated_covered_amount_at_booking_and_more"
YAKAP_0003 = "0003_normalize_default_yakap_category_limits"


@pytest.mark.django_db(transaction=True)
def test_0003_resets_legacy_default_non_medicine_category_limits():
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([("yakap", YAKAP_0002)])
        old_apps = executor.loader.project_state([("yakap", YAKAP_0002)]).apps
        user_app, user_model = settings.AUTH_USER_MODEL.split(".")
        User = old_apps.get_model(user_app, user_model)
        ClinicGroup = old_apps.get_model("clinics", "ClinicGroup")
        Clinic = old_apps.get_model("clinics", "Clinic")
        ClinicYakapSettings = old_apps.get_model("yakap", "ClinicYakapSettings")
        YakapCoverageCategory = old_apps.get_model("yakap", "YakapCoverageCategory")

        owner = User.objects.create(username="migration-yakap-owner@example.com", email="migration-yakap-owner@example.com")
        group = ClinicGroup.objects.create(name="Migration YAKAP Group", owner=owner)
        clinic = Clinic.objects.create(group=group, name="Migration YAKAP Clinic", slug="migration-yakap-clinic")
        custom_clinic = Clinic.objects.create(
            group=group,
            name="Migration Custom YAKAP Clinic",
            slug="migration-custom-yakap-clinic",
        )
        ClinicYakapSettings.objects.create(clinic=custom_clinic, default_non_medicine_limit=Decimal("20000.00"))
        for name, category_type, sort_order in [
            ("Primary Care", "primary_care", 0),
            ("Laboratory", "laboratory", 1),
            ("Medicines", "medicines", 2),
            ("Cancer Screening", "cancer_screening", 3),
        ]:
            for target_clinic in [clinic, custom_clinic]:
                YakapCoverageCategory.objects.create(
                    clinic=target_clinic,
                    name=name,
                    category_type=category_type,
                    annual_limit=Decimal("20000.00"),
                    sort_order=sort_order,
                )

        executor.loader.build_graph()
        executor.migrate([("yakap", YAKAP_0003)])
        new_apps = executor.loader.project_state([("yakap", YAKAP_0003)]).apps
        MigratedCategory = new_apps.get_model("yakap", "YakapCoverageCategory")

        limits = {
            category.name: category.annual_limit
            for category in MigratedCategory.objects.filter(clinic_id=clinic.id)
        }
        assert limits["Medicines"] == Decimal("20000.00")
        assert limits["Primary Care"] == Decimal("0.00")
        assert limits["Laboratory"] == Decimal("0.00")
        assert limits["Cancer Screening"] == Decimal("0.00")
        custom_limits = {
            category.name: category.annual_limit
            for category in MigratedCategory.objects.filter(clinic_id=custom_clinic.id)
        }
        assert custom_limits["Medicines"] == Decimal("20000.00")
        assert custom_limits["Primary Care"] == Decimal("20000.00")
        assert custom_limits["Laboratory"] == Decimal("20000.00")
        assert custom_limits["Cancer Screening"] == Decimal("20000.00")
    finally:
        executor.loader.build_graph()
        executor.migrate(leaf_nodes)
