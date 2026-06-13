import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from accounts.models import User
from clinics.models import Clinic, ClinicGroup, ClinicMembership
from messenger.models import MessengerConnection
from patients.models import Patient


@pytest.mark.django_db
def test_non_superuser_staff_cannot_access_tenant_patient_admin(client):
    owner = User.objects.create_user(username="owner-admin@example.com", email="owner-admin@example.com", password="pass")
    group = ClinicGroup.objects.create(name="Admin Group", owner=owner)
    clinic = Clinic.objects.create(group=group, name="Admin Clinic", slug="admin-clinic")
    staff = User.objects.create_user(
        username="staff-admin@example.com",
        email="staff-admin@example.com",
        password="pass",
        is_staff=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    staff.user_permissions.add(Permission.objects.get(codename="view_patient"))
    Patient.objects.create(clinic=clinic, full_name="Admin Visible Patient", phone="09170000000")
    client.force_login(staff)

    response = client.get(reverse("admin:patients_patient_changelist"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_non_superuser_staff_cannot_access_messenger_connection_admin(client):
    owner = User.objects.create_user(username="owner-msg-admin@example.com", email="owner-msg-admin@example.com", password="pass")
    group = ClinicGroup.objects.create(name="Messenger Admin Group", owner=owner)
    clinic = Clinic.objects.create(group=group, name="Messenger Admin Clinic", slug="messenger-admin-clinic")
    staff = User.objects.create_user(
        username="staff-msg-admin@example.com",
        email="staff-msg-admin@example.com",
        password="pass",
        is_staff=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    staff.user_permissions.add(Permission.objects.get(codename="view_messengerconnection"))
    MessengerConnection.objects.create(
        clinic=clinic,
        app_secret="SECRET",
        page_id="PAGE-ADMIN",
        page_access_token="TOKEN-ADMIN",
    )
    client.force_login(staff)

    response = client.get(reverse("admin:messenger_messengerconnection_changelist"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_non_superuser_staff_cannot_access_user_admin(client):
    staff = User.objects.create_user(
        username="staff-user-admin@example.com",
        email="staff-user-admin@example.com",
        password="pass",
        is_staff=True,
    )
    staff.user_permissions.add(Permission.objects.get(codename="view_user"))
    client.force_login(staff)

    response = client.get(reverse("admin:accounts_user_changelist"))

    assert response.status_code == 403
