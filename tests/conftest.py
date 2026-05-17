import pytest
from datetime import time, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from scheduling.models import ClinicBusinessHour
from services.models import Service


@pytest.fixture
def clinic_setup(db):
    User = get_user_model()
    user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    weekday = (timezone.localdate() + timedelta(days=1)).weekday()
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=weekday, open_time=time(9), close_time=time(12))
    return clinic, service
