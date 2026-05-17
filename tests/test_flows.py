import pytest
from django.urls import reverse

from clinics.models import Clinic


@pytest.mark.django_db
def test_signup_creates_usable_clinic(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "demo@example.com",
            "clinic_name": "Demo Clinic",
            "password": "password123",
        },
    )
    assert response.status_code == 302
    clinic = Clinic.objects.get(slug="demo-clinic")
    assert clinic.services.filter(name="General Consultation").exists()
    assert clinic.business_hours.count() == 5
