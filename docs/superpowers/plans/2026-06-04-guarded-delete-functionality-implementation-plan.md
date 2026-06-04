# Guarded Delete Functionality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add guarded delete functionality for services, appointments, and patients while preserving clinic history and tenant boundaries.

**Architecture:** Add three POST-only dashboard delete endpoints that scope all lookups through the active clinic and reuse existing HTMX partial-refresh patterns. Services and patients are guarded by appointment-history checks; appointments can be permanently deleted from confirmation UI while cancellation remains the normal operational removal path.

**Tech Stack:** Django, Django templates, HTMX, Alpine.js, pytest, existing `cf-*` design system classes.

---

## Scope Check

This plan covers one cohesive feature across three dashboard domains. Each domain is implemented as a separate task so services, appointments, and patients remain independently testable.

## File Structure

- Modify `dashboard/urls.py`: add `delete_service`, `delete_appointment`, and `delete_patient` routes.
- Modify `dashboard/views.py`: add clinic-scoped delete views plus small context helpers for appointment, patient, and service partial refreshes.
- Modify `templates/dashboard/partials/service_row.html`: add archived-service delete confirmation modal.
- Modify `templates/dashboard/partials/appointment_detail.html`: add appointment delete mode and confirmation form.
- Modify `templates/dashboard/appointments.html`: close the appointment detail modal after successful HTMX delete.
- Modify `templates/dashboard/partials/patient_detail.html`: add patient-delete modal state.
- Modify `templates/dashboard/partials/patient_detail_content.html`: add patient detail delete action and confirmation modal; mark patient history appointment links as `source=patient`.
- Modify `templates/dashboard/partials/patient_list.html`: add list-row delete action with confirmation.
- Modify `templates/dashboard/partials/patient_row.html`: keep HTMX-updated patient rows consistent with the list-row delete action.
- Modify `services/tests.py`: cover service guarded delete behavior.
- Modify `dashboard/tests.py`: cover appointment delete behavior and HTMX refresh semantics.
- Modify `patients/tests.py`: cover patient guarded delete behavior.
- Modify `tests/test_design_system.py`: lock in confirmation UI and no unsafe GET delete links.

## Task 1: Add Guarded Service Delete

**Files:**
- Modify: `services/tests.py`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/views.py`
- Modify: `templates/dashboard/partials/service_row.html`
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Write failing service delete tests**

Add these imports near the top of `services/tests.py`:

```python
from django.utils import timezone

from appointments.models import Appointment
from patients.models import Patient
```

Add these test methods inside `ServiceTests` after `test_restore_service_htmx`:

```python
    def test_delete_archived_service_without_appointments(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived", "updated_at"])
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())

    def test_delete_active_service_is_blocked_until_archived(self):
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_archived)

    def test_delete_service_with_appointments_is_blocked(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived", "updated_at"])
        patient = Patient.objects.create(clinic=self.clinic, full_name="Service History", phone="09170009999")
        starts_at = timezone.now() + timezone.timedelta(days=1)
        Appointment.objects.create(
            clinic=self.clinic,
            patient=patient,
            service=self.service,
            starts_at=starts_at,
            ends_at=starts_at + timezone.timedelta(minutes=30),
        )
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

    def test_delete_service_requires_post(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived", "updated_at"])
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

    def test_delete_service_htmx_refreshes_service_list(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived", "updated_at"])
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Retarget", response.headers)
        self.assertEqual(response.headers["HX-Retarget"], "#services-list-container")
        self.assertIn("Service deleted.", response.headers["HX-Trigger"])
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())
```

Update `test_unauthenticated_access_denied` in `services/tests.py` so `delete_service` is included:

```python
        for url_name in ["services", "create_service", "toggle_service", "archive_service", "restore_service", "delete_service"]:
```

Update `test_service_clinic_isolation_expanded` in `services/tests.py` so `delete_service` is included:

```python
        for url_name in ["edit_service", "toggle_service", "archive_service", "restore_service", "delete_service"]:
```

- [ ] **Step 2: Run service delete tests to verify they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest services/tests.py -k "delete_service or service_clinic_isolation_expanded or unauthenticated_access_denied" -q
```

Expected: FAIL with `NoReverseMatch` for `dashboard:delete_service`.

- [ ] **Step 3: Add service delete route**

In `dashboard/urls.py`, add this path immediately after `restore_service`:

```python
    path("services/<int:pk>/delete/", views.delete_service, name="delete_service"),
```

- [ ] **Step 4: Add service delete view**

In `dashboard/views.py`, add this helper near `restore_service` or immediately before `delete_service`:

```python
def _service_list_response(request, clinic, message, *, toast_type="success"):
    active_services = clinic.services.filter(is_archived=False).select_related("clinic")
    archived_services = clinic.services.filter(is_archived=True).select_related("clinic")
    membership = get_active_membership(request.user)
    response = render(
        request,
        "dashboard/partials/service_list.html",
        {
            "clinic": clinic,
            "active_services": active_services,
            "archived_services": archived_services,
            "form": ServiceForm(clinic),
            "can_manage": user_can_manage_daily_ops(membership),
        },
    )
    response["HX-Retarget"] = "#services-list-container"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = json.dumps({
        "toast-message": {"message": message, "type": toast_type}
    })
    return response
```

Add this view immediately after `restore_service`:

```python
@login_required
@require_POST
def delete_service(request, pk):
    clinic = _clinic_or_redirect(request)
    service = get_object_or_404(clinic.services, pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if not service.is_archived:
        message = "Archive this service before deleting it permanently."
        if request.headers.get("HX-Request"):
            return _service_list_response(request, clinic, message, toast_type="error")
        messages.error(request, message)
        return redirect("dashboard:services")
    if service.appointments.exists():
        message = "Services with appointment history cannot be deleted. Keep it archived for records."
        if request.headers.get("HX-Request"):
            return _service_list_response(request, clinic, message, toast_type="error")
        messages.error(request, message)
        return redirect("dashboard:services")
    service.delete()
    if request.headers.get("HX-Request"):
        return _service_list_response(request, clinic, "Service deleted.")
    messages.success(request, "Service deleted.")
    return redirect("dashboard:services")
```

- [ ] **Step 5: Run service delete tests to verify backend passes**

Run:

```powershell
.\env\Scripts\python.exe -m pytest services/tests.py -k "delete_service or service_clinic_isolation_expanded or unauthenticated_access_denied" -q
```

Expected: PASS.

- [ ] **Step 6: Add service delete UI tests**

In `tests/test_design_system.py`, add this test near `test_service_row_toggle_button_uses_stateful_action_styles`:

```python
def test_archived_service_row_has_guarded_delete_confirmation():
    template = partial_text("service_row.html")

    archived_start = template.index("{% else %}")
    archived_block = template[archived_start:]

    assert "dashboard:delete_service" in archived_block
    assert "Delete service" in archived_block
    assert "This permanently deletes the service only if it has no appointment history." in archived_block
    assert "cf-btn cf-btn-xs cf-btn-danger" in archived_block
    assert "csrf_token" in archived_block
    assert "hx-post=\"{% url 'dashboard:delete_service' service.id %}\"" in archived_block
    assert "href=\"{% url 'dashboard:delete_service'" not in template
```

- [ ] **Step 7: Run service UI test to verify it fails**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_archived_service_row_has_guarded_delete_confirmation -q
```

Expected: FAIL because the template has no delete confirmation.

- [ ] **Step 8: Add archived service delete confirmation modal**

In `templates/dashboard/partials/service_row.html`, change the opening `<article>` to include Alpine state:

```html
<article id="service-card-{{ service.id }}" x-data="{deleting:false}" class="cf-card p-5 flex flex-col">
```

Inside the archived-service branch, after the restore form, add:

```html
      <button type="button" @click="deleting=true" class="cf-btn cf-btn-xs cf-btn-danger"><i data-lucide="trash-2" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Delete</button>
      <div x-show="deleting" x-cloak class="cf-modal-backdrop" @click.self="deleting=false">
        <div class="cf-modal cf-modal-sm" role="dialog" aria-modal="true" aria-labelledby="delete-service-title-{{ service.id }}" @click.stop>
          <div class="cf-modal-header flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="cf-icon-box h-10 w-10 bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-red)]">
                <i data-lucide="trash-2" class="h-5 w-5"></i>
              </div>
              <h3 id="delete-service-title-{{ service.id }}" class="cf-modal-title">Delete service</h3>
            </div>
            <button type="button" @click="deleting=false" class="cf-icon-btn" aria-label="Close delete service modal">
              <i data-lucide="x" class="h-5 w-5"></i>
            </button>
          </div>
          <div class="cf-modal-body">
            <p class="cf-muted">This permanently deletes the service only if it has no appointment history.</p>
          </div>
          <div class="cf-modal-footer">
            <button type="button" @click="deleting=false" class="cf-btn cf-btn-secondary"><i data-lucide="x-circle" class="h-4 w-4"></i>Cancel</button>
            <form method="post" action="{% url 'dashboard:delete_service' service.id %}" hx-post="{% url 'dashboard:delete_service' service.id %}" hx-target="#services-list-container" hx-swap="innerHTML" class="inline">
              {% csrf_token %}
              <button type="submit" class="cf-btn cf-btn-danger"><i data-lucide="trash-2" class="h-4 w-4"></i>Delete</button>
            </form>
          </div>
        </div>
      </div>
```

- [ ] **Step 9: Run service tests and UI test**

Run:

```powershell
.\env\Scripts\python.exe -m pytest services/tests.py tests/test_design_system.py::test_archived_service_row_has_guarded_delete_confirmation -q
```

Expected: PASS.

- [ ] **Step 10: Commit service delete changes only if commits are explicitly approved**

Run only after explicit commit approval:

```powershell
git add services/tests.py dashboard/urls.py dashboard/views.py templates/dashboard/partials/service_row.html tests/test_design_system.py
git commit -m "feat: add guarded service delete"
```

Expected: commit succeeds.

## Task 2: Add Appointment Delete From Detail Modal

**Files:**
- Modify: `dashboard/tests.py`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/views.py`
- Modify: `templates/dashboard/appointments.html`
- Modify: `templates/dashboard/partials/appointment_detail.html`
- Modify: `templates/dashboard/partials/patient_detail.html`
- Modify: `templates/dashboard/partials/patient_detail_content.html`
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Write failing appointment delete tests**

Update the appointment import in `dashboard/tests.py`:

```python
from appointments.models import Appointment, AppointmentNote
```

Add these tests after `test_appointment_detail_rejects_unsafe_mode`:

```python
@pytest.mark.django_db
def test_delete_appointment_requires_post(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:delete_appointment", args=[appointment.id]))

    assert response.status_code == 405
    assert Appointment.objects.filter(pk=appointment.pk).exists()


@pytest.mark.django_db
def test_delete_appointment_removes_appointment_and_notes(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    note = AppointmentNote.objects.create(appointment=appointment, author=user, body="Mistaken booking")
    client.force_login(user)

    response = client.post(reverse("dashboard:delete_appointment", args=[appointment.id]))

    assert response.status_code == 302
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert not AppointmentNote.objects.filter(pk=note.pk).exists()


@pytest.mark.django_db
def test_htmx_delete_appointment_refreshes_appointments_table(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert b"Appointments" in response.content
    assert "appointmentDeleted" in response.headers["HX-Trigger"]
    assert "Appointment deleted." in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_calendar_delete_appointment_triggers_refetch_and_close(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        {"modal_source": "calendar"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    trigger = response.headers["HX-Trigger"]
    assert "calendar-refetch" in trigger
    assert "close-calendar-modal" in trigger
    assert "Appointment deleted." in trigger
    assert "HX-Retarget" not in response.headers


@pytest.mark.django_db
def test_patient_history_delete_appointment_refreshes_patient_detail(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        {"modal_source": "patient"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert b"Contact Details" in response.content
    assert b"No visits yet" in response.content
    assert "appointmentDeleted" in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_delete_appointment_cross_clinic_isolation(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_user = get_user_model().objects.create_user(username="delete-other@example.com", email="delete-other@example.com", password="password123")
    other_group = ClinicGroup.objects.create(name="Other Delete Clinic", owner=other_user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Delete Clinic", slug="other-delete-clinic")
    ClinicMembership.objects.create(clinic=other_clinic, user=other_user, role=ClinicMembership.ROLE_OWNER)
    client.force_login(other_user)

    response = client.post(reverse("dashboard:delete_appointment", args=[appointment.id]))

    assert response.status_code == 404
    assert Appointment.objects.filter(pk=appointment.pk).exists()
```

- [ ] **Step 2: Run appointment delete tests to verify they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "delete_appointment" -q
```

Expected: FAIL with `NoReverseMatch` for `dashboard:delete_appointment`.

- [ ] **Step 3: Add appointment context helpers**

In `dashboard/views.py`, add these helpers above `appointments`:

```python
def _request_filter_params(request):
    if request.method == "POST" and request.headers.get("HX-Request"):
        return request.POST
    return request.GET


def _appointments_context(request, clinic):
    params = _request_filter_params(request)
    qs = clinic.appointments.select_related("patient", "service").all()
    search_query = params.get("q", "").strip()
    if search_query:
        qs = qs.filter(
            Q(patient__full_name__icontains=search_query)
            | Q(patient__phone__icontains=search_query)
            | Q(service__name__icontains=search_query)
            | Q(reference_code__icontains=search_query)
        )
    status = params.get("status")
    if status:
        qs = qs.filter(status=status)
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if date_from:
        qs = qs.filter(starts_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(starts_at__date__lte=date_to)
    service_filter = params.get("service")
    if service_filter:
        qs = qs.filter(service_id=service_filter)
    source_filter = params.get("source")
    if source_filter:
        qs = qs.filter(source=source_filter)
    payment_filter = params.get("payment_state")
    if payment_filter:
        qs = qs.filter(payment_state=payment_filter)
    qs = qs.order_by("-starts_at")
    paginator = Paginator(qs, 10)
    page_number = params.get("page", 1)
    page_obj = paginator.get_page(page_number)
    return {
        "clinic": clinic,
        "appointments": page_obj,
        "page_obj": page_obj,
        "form": StaffAppointmentForm(clinic),
        "patient_form": PatientForm(clinic=clinic),
        "services": clinic.services.filter(is_archived=False),
        "search_query": search_query,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "service_filter": service_filter,
        "source_filter": source_filter,
        "payment_filter": payment_filter,
        "status_choices": Appointment.STATUS_CHOICES,
        "source_choices": Appointment.SOURCE_CHOICES,
        "payment_choices": Appointment.PAYMENT_CHOICES,
    }


def _patient_detail_context(clinic, patient):
    appointments = patient.appointments.all()
    return {
        "clinic": clinic,
        "patient": patient,
        "kpi_total": appointments.count(),
        "kpi_upcoming": appointments.filter(status__in=["pending", "confirmed"], starts_at__gte=timezone.now()).count(),
        "kpi_completed": appointments.filter(status="completed").count(),
        "kpi_cancelled": appointments.filter(status__in=["cancelled", "no_show"]).count(),
        "last_appointment": appointments.order_by("starts_at").last(),
    }
```

Replace the body of `appointments` after `clinic = _clinic_or_redirect(request)` with:

```python
    context = _appointments_context(request, clinic)
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/appointment_list.html", context)
    return render(request, "dashboard/appointments.html", context)
```

Replace the context construction in `patient_detail` with:

```python
    context = _patient_detail_context(clinic, patient)
    return render(request, "dashboard/partials/patient_detail.html", context)
```

- [ ] **Step 4: Add appointment delete route and view**

In `dashboard/urls.py`, add this path immediately after `appointment_cancel`:

```python
    path("appointments/<int:pk>/delete/", views.delete_appointment, name="delete_appointment"),
```

In `dashboard/views.py`, add this view immediately after `appointment_cancel`:

```python
@login_required
@require_POST
def delete_appointment(request, pk):
    clinic = _clinic_or_redirect(request)
    appointment = get_object_or_404(clinic.appointments.select_related("patient"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    patient_id = appointment.patient_id
    appointment.delete()
    if request.headers.get("HX-Request"):
        modal_source = request.POST.get("modal_source", "")
        if modal_source == "calendar":
            response = HttpResponse("")
            response["HX-Trigger"] = _calendar_modal_trigger("Appointment deleted.", close=True)
            return response
        if modal_source == "patient":
            patient = get_object_or_404(
                clinic.patients.prefetch_related("appointments__service"),
                pk=patient_id,
            )
            response = render(
                request,
                "dashboard/partials/patient_detail_content.html",
                _patient_detail_context(clinic, patient),
            )
            response["HX-Trigger"] = json.dumps({
                "appointmentDeleted": True,
                "toast-message": {"message": "Appointment deleted.", "type": "success"},
            })
            return response
        response = render(request, "dashboard/partials/appointment_list.html", _appointments_context(request, clinic))
        response["HX-Trigger"] = json.dumps({
            "appointmentDeleted": True,
            "toast-message": {"message": "Appointment deleted.", "type": "success"},
        })
        return response
    messages.success(request, "Appointment deleted.")
    return redirect("dashboard:appointments")
```

- [ ] **Step 5: Run appointment backend tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "delete_appointment or appointment_detail_returns_partial or appointment_detail_rejects_unsafe_mode" -q
```

Expected: PASS.

- [ ] **Step 6: Write appointment delete UI tests**

In `tests/test_design_system.py`, add these tests near appointment detail tests:

```python
def test_appointment_detail_has_separate_delete_mode():
    template = partial_text("appointment_detail.html")

    assert "Delete appointment" in template
    assert "Delete permanently" in template
    assert "dashboard:delete_appointment" in template
    assert "mode === 'delete'" in template
    assert "modal_source" in template
    assert "hx-include=\"#filter-form\"" in template
    assert "cf-btn cf-btn-danger" in template
    assert "href=\"{% url 'dashboard:delete_appointment'" not in template


def test_appointment_delete_success_closes_open_detail_modals():
    appointments = source_text("templates/dashboard/appointments.html")
    patient_detail = partial_text("patient_detail.html")

    assert 'x-on:appointment-deleted.camel="detailOpen=false"' in appointments
    assert 'x-on:appointment-deleted.camel="detailOpen=false"' in patient_detail


def test_patient_visit_history_marks_appointment_detail_source():
    template = partial_text("patient_detail_content.html")

    assert "dashboard:appointment_detail' appointment.id %}?source=patient" in template
```

- [ ] **Step 7: Run appointment UI tests to verify they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -k "appointment_detail_has_separate_delete_mode or appointment_delete_success_closes_open_detail_modals or patient_visit_history_marks_appointment_detail_source" -q
```

Expected: FAIL because templates have no appointment delete mode yet.

- [ ] **Step 8: Add appointment modal close event handlers**

In `templates/dashboard/appointments.html`, change the root `<div>` opening tag so it includes the appointment deleted event handler:

```html
<div x-data="{open:false, filtersOpen:false, detailOpen:false, patientOpen:false, queryParams() { const form = document.getElementById('filter-form'); const params = new URLSearchParams(new FormData(form)); Array.from(params.keys()).forEach((key) => { if (!params.get(key)) params.delete(key); }); return params; }, exportHref() { const query = this.queryParams().toString(); return '{% url 'dashboard:export_csv' %}' + (query ? '?' + query : ''); }, trapModalFocus(event, root) { const focusable = Array.from(root.querySelectorAll(`a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])`)).filter((el) => el.offsetParent !== null); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }" class="cf-page" x-on:appointment-deleted.camel="detailOpen=false">
```

In `templates/dashboard/partials/patient_detail.html`, change the root `<div>` opening tag so it includes the appointment deleted event handler:

```html
<div x-data="{detailOpen:false, editOpen:false, patientDeleteOpen:false, trapModalFocus(event, root) { const focusable = Array.from(root.querySelectorAll(`a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])`)).filter((el) => el.offsetParent !== null); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }" @keydown.escape.window="detailOpen=false; editOpen=false; patientDeleteOpen=false" x-on:appointment-deleted.camel="detailOpen=false">
```

- [ ] **Step 9: Add appointment delete mode**

In `templates/dashboard/partials/appointment_detail.html`, update the title expression on line 2 to include delete mode:

```html
  <h2 id="appointment-detail-title" class="sr-only" x-text="mode === 'cancel' ? 'Cancel appointment' : (mode === 'reschedule' ? 'Reschedule appointment' : (mode === 'delete' ? 'Delete appointment' : 'Appointment Details'))">Appointment Details</h2>
```

At the end of the detail mode body, before the closing `</div>` for `mode === 'detail'`, add:

```html
      <div class="cf-modal-footer border-t border-[var(--cf-line-soft)] pt-5">
        <button type="button" @click="detailOpen=false" class="cf-btn cf-btn-secondary flex-1"><i data-lucide="x-circle" class="h-4 w-4"></i>Close</button>
        <button type="button" @click="mode = 'delete'" class="cf-btn cf-btn-danger flex-1"><i data-lucide="trash-2" class="h-4 w-4"></i>Delete permanently</button>
      </div>
```

After the cancel mode block and before the reschedule mode block, add:

```html
  <!-- Delete Mode -->
  <div x-show="mode === 'delete'" x-cloak>
    <div class="cf-modal-header flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="cf-icon-box h-10 w-10 rounded-full bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-red)]">
          <i data-lucide="trash-2" class="h-5 w-5"></i>
        </div>
        <div>
          <h3 id="delete-appointment-title" class="cf-modal-title">Delete appointment</h3>
          <p class="text-sm text-[var(--cf-muted)]">This permanently deletes the appointment and its internal notes.</p>
        </div>
      </div>
      <button type="button" @click="detailOpen=false" class="cf-icon-btn" aria-label="Close">
        <i data-lucide="x" class="h-5 w-5"></i>
      </button>
    </div>
    <form method="post" action="{% url 'dashboard:delete_appointment' appointment.id %}"
          hx-post="{% url 'dashboard:delete_appointment' appointment.id %}"
          {% if source == 'calendar' %}hx-target="#delete-error"{% elif source == 'patient' %}hx-target="#patient-detail-content"{% else %}hx-target="#appointments-table" hx-include="#filter-form"{% endif %}
          hx-swap="innerHTML">
      {% csrf_token %}
      {% if source %}<input type="hidden" name="modal_source" value="{{ source }}">{% endif %}
      <div class="cf-modal-body space-y-4">
        <div class="rounded-[var(--cf-radius)] bg-[var(--cf-surface-muted)] p-4">
          <p class="break-words text-sm text-[var(--cf-muted)]">Patient: <strong class="text-[var(--cf-ink)]">{{ appointment.patient.full_name }}</strong></p>
          <p class="break-words text-sm text-[var(--cf-muted)]">Service: <strong class="text-[var(--cf-ink)]">{{ appointment.service.name }}</strong></p>
          <p class="break-words text-sm text-[var(--cf-muted)]">Date: <strong class="text-[var(--cf-ink)]">{{ appointment.starts_at|date:"M j, Y g:i A" }}</strong></p>
        </div>
        <div id="delete-error" class="cf-error"></div>
      </div>
      <div class="cf-modal-footer">
        <button type="button" @click="mode = 'detail'" class="cf-btn cf-btn-secondary flex-1"><i data-lucide="arrow-left" class="h-4 w-4"></i>Back</button>
        <button type="submit" class="cf-btn cf-btn-danger flex-1"><i data-lucide="trash-2" class="h-4 w-4"></i>Delete permanently</button>
      </div>
    </form>
  </div>
```

In `templates/dashboard/partials/patient_detail_content.html`, update both patient-history appointment detail `hx-get` attributes to pass `source=patient`:

```html
hx-get="{% url 'dashboard:appointment_detail' appointment.id %}?source=patient"
```

- [ ] **Step 10: Run appointment backend and UI tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "delete_appointment" tests/test_design_system.py -k "appointment_detail_has_separate_delete_mode or appointment_delete_success_closes_open_detail_modals or patient_visit_history_marks_appointment_detail_source" -q
```

Expected: PASS.

- [ ] **Step 11: Commit appointment delete changes only if commits are explicitly approved**

Run only after explicit commit approval:

```powershell
git add dashboard/tests.py dashboard/urls.py dashboard/views.py templates/dashboard/appointments.html templates/dashboard/partials/appointment_detail.html templates/dashboard/partials/patient_detail.html templates/dashboard/partials/patient_detail_content.html tests/test_design_system.py
git commit -m "feat: add guarded appointment delete"
```

Expected: commit succeeds.

## Task 3: Add Guarded Patient Delete

**Files:**
- Modify: `patients/tests.py`
- Modify: `dashboard/urls.py`
- Modify: `dashboard/views.py`
- Modify: `templates/dashboard/partials/patient_list.html`
- Modify: `templates/dashboard/partials/patient_row.html`
- Modify: `templates/dashboard/partials/patient_detail_content.html`
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Write failing patient delete tests**

Add these tests after `test_merge_scoped_to_clinic` in `patients/tests.py`:

```python
@pytest.mark.django_db
def test_patient_delete_without_appointments_deletes_patient(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Delete Me", phone="09170008888")

    response = client.post(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 302
    assert not Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_with_appointments_is_blocked(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="History Patient", phone="09170007777")
    starts_at = timezone.now() + timezone.timedelta(days=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timezone.timedelta(minutes=30),
    )

    response = client.post(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 302
    assert Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_requires_post(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Delete By Post", phone="09170006666")

    response = client.get(reverse("dashboard:delete_patient", args=[patient.id]))

    assert response.status_code == 405
    assert Patient.objects.filter(pk=patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_cross_clinic_returns_404(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    other_group = ClinicGroup.objects.create(name="Other Clinic", owner=user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-patient-delete")
    other_patient = Patient.objects.create(clinic=other_clinic, full_name="Other Patient", phone="09170005555")

    response = client.post(reverse("dashboard:delete_patient", args=[other_patient.id]))

    assert response.status_code == 404
    assert Patient.objects.filter(pk=other_patient.pk).exists()


@pytest.mark.django_db
def test_patient_delete_htmx_refreshes_patient_list(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="HTMX Delete", phone="09170004444")

    response = client.post(
        reverse("dashboard:delete_patient", args=[patient.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Patient.objects.filter(pk=patient.pk).exists()
    assert b"Patients" in response.content
    assert "Patient deleted." in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_patient_delete_htmx_blocked_keeps_patient_list(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Blocked Delete", phone="09170003333")
    starts_at = timezone.now() + timezone.timedelta(days=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timezone.timedelta(minutes=30),
    )

    response = client.post(
        reverse("dashboard:delete_patient", args=[patient.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert Patient.objects.filter(pk=patient.pk).exists()
    assert response.headers["HX-Reswap"] == "none"
    assert "appointment history" in response.headers["HX-Trigger"]
```

- [ ] **Step 2: Run patient delete tests to verify they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest patients/tests.py -k "patient_delete" -q
```

Expected: FAIL with `NoReverseMatch` for `dashboard:delete_patient`.

- [ ] **Step 3: Add patient list context helper**

In `dashboard/views.py`, add this helper above `patients`:

```python
def _patients_context(request, clinic):
    params = _request_filter_params(request)
    query = params.get("q", "").strip()
    qs = clinic.patients.order_by("-created_at", "-id")
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    paginator = Paginator(qs, 10)
    page_number = params.get("page", 1)
    page_obj = paginator.get_page(page_number)
    return {
        "clinic": clinic,
        "patients": page_obj,
        "page_obj": page_obj,
        "patient_form": PatientForm(clinic=clinic),
        "query": query,
    }
```

Replace the body of `patients` after `clinic = _clinic_or_redirect(request)` with:

```python
    context = _patients_context(request, clinic)
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/patient_list.html", context)
    return render(request, "dashboard/patients.html", context)
```

- [ ] **Step 4: Add patient delete route and view**

In `dashboard/urls.py`, add this path immediately after `patient_edit`:

```python
    path("patients/<int:pk>/delete/", views.delete_patient, name="delete_patient"),
```

In `dashboard/views.py`, add this view immediately after `patient_edit`:

```python
@login_required
@require_POST
def delete_patient(request, pk):
    clinic = _clinic_or_redirect(request)
    patient = get_object_or_404(clinic.patients, pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if patient.appointments.exists():
        message = "Patients with appointment history cannot be deleted. Merge duplicates instead."
        if request.headers.get("HX-Request"):
            response = HttpResponse("")
            response["HX-Reswap"] = "none"
            response["HX-Trigger"] = json.dumps({
                "toast-message": {"message": message, "type": "error"}
            })
            return response
        messages.error(request, message)
        return redirect("dashboard:patient_detail", pk=patient.pk)
    patient.delete()
    if request.headers.get("HX-Request"):
        response = render(request, "dashboard/partials/patient_list.html", _patients_context(request, clinic))
        response["HX-Trigger"] = json.dumps({
            "patientDeleted": True,
            "toast-message": {"message": "Patient deleted.", "type": "success"},
        })
        return response
    messages.success(request, "Patient deleted.")
    return redirect("dashboard:patients")
```

- [ ] **Step 5: Run patient backend tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest patients/tests.py -k "patient_delete or merge" -q
```

Expected: PASS.

- [ ] **Step 6: Write patient delete UI tests**

In `tests/test_design_system.py`, add these tests near the patient mobile/design tests:

```python
def test_patient_rows_have_guarded_delete_confirmation():
    patient_list = partial_text("patient_list.html")
    patient_row = partial_text("patient_row.html")

    for template in [patient_list, patient_row]:
        assert "dashboard:delete_patient" in template
        assert "Delete patient" in template
        assert "Patients with appointment history cannot be deleted." in template
        assert "cf-btn cf-btn-xs cf-btn-danger" in template
        assert "hx-target=\"#patient-list\"" in template
        assert "hx-include=\"#patient-toolbar\"" in template
        assert "csrf_token" in template
        assert "href=\"{% url 'dashboard:delete_patient'" not in template


def test_patient_detail_has_guarded_delete_confirmation():
    detail = partial_text("patient_detail.html")
    content = partial_text("patient_detail_content.html")

    assert "patientDeleteOpen:false" in detail
    assert "patientDeleteOpen=false" in detail
    assert "dashboard:delete_patient" in content
    assert "Delete patient" in content
    assert "Patients with appointment history cannot be deleted." in content
    assert "cf-btn cf-btn-danger" in content
    assert "csrf_token" in content
```

- [ ] **Step 7: Run patient UI tests to verify they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -k "patient_rows_have_guarded_delete_confirmation or patient_detail_has_guarded_delete_confirmation" -q
```

Expected: FAIL because templates have no patient delete controls yet.

- [ ] **Step 8: Add patient delete controls to list rows**

In both `templates/dashboard/partials/patient_list.html` and `templates/dashboard/partials/patient_row.html`, inside the action cell after the Edit button, add this delete control:

```html
                <span x-data="{deleting:false}" class="inline">
                  <button type="button" @click="deleting=true" class="cf-btn cf-btn-xs cf-btn-danger"><i data-lucide="trash-2" class="h-3 w-3 shrink-0" aria-hidden="true"></i>Delete</button>
                  <div x-show="deleting" x-cloak class="cf-modal-backdrop" @click.self="deleting=false">
                    <div class="cf-modal cf-modal-sm" role="dialog" aria-modal="true" aria-labelledby="delete-patient-title-{{ patient.id }}" @click.stop>
                      <div class="cf-modal-header flex items-center justify-between">
                        <div class="flex items-center gap-3">
                          <div class="cf-icon-box h-10 w-10 bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-red)]">
                            <i data-lucide="trash-2" class="h-5 w-5"></i>
                          </div>
                          <h3 id="delete-patient-title-{{ patient.id }}" class="cf-modal-title">Delete patient</h3>
                        </div>
                        <button type="button" @click="deleting=false" class="cf-icon-btn" aria-label="Close delete patient modal">
                          <i data-lucide="x" class="h-5 w-5"></i>
                        </button>
                      </div>
                      <div class="cf-modal-body">
                        <p class="cf-muted">Patients with appointment history cannot be deleted. Use merge for duplicates with history.</p>
                      </div>
                      <div class="cf-modal-footer">
                        <button type="button" @click="deleting=false" class="cf-btn cf-btn-secondary"><i data-lucide="x-circle" class="h-4 w-4"></i>Cancel</button>
                        <form method="post" action="{% url 'dashboard:delete_patient' patient.id %}" hx-post="{% url 'dashboard:delete_patient' patient.id %}" hx-target="#patient-list" hx-swap="innerHTML" hx-include="#patient-toolbar" class="inline">
                          {% csrf_token %}
                          <button type="submit" class="cf-btn cf-btn-danger"><i data-lucide="trash-2" class="h-4 w-4"></i>Delete</button>
                        </form>
                      </div>
                    </div>
                  </div>
                </span>
```

- [ ] **Step 9: Add patient delete control to detail page**

In `templates/dashboard/partials/patient_detail_content.html`, add this button inside `.cf-page-actions` after Edit:

```html
      <button type="button" @click="patientDeleteOpen=true" class="cf-btn cf-btn-danger">
        <i data-lucide="trash-2" class="h-4 w-4"></i>
        Delete
      </button>
```

After the page header in `patient_detail_content.html`, add this modal:

```html
  <div x-show="patientDeleteOpen" x-cloak class="cf-modal-backdrop" @click.self="patientDeleteOpen=false">
    <div class="cf-modal cf-modal-sm" role="dialog" aria-modal="true" aria-labelledby="delete-patient-detail-title" @click.stop>
      <div class="cf-modal-header flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="cf-icon-box h-10 w-10 bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-red)]">
            <i data-lucide="trash-2" class="h-5 w-5"></i>
          </div>
          <h3 id="delete-patient-detail-title" class="cf-modal-title">Delete patient</h3>
        </div>
        <button type="button" @click="patientDeleteOpen=false" class="cf-icon-btn" aria-label="Close delete patient modal">
          <i data-lucide="x" class="h-5 w-5"></i>
        </button>
      </div>
      <div class="cf-modal-body">
        <p class="cf-muted">Patients with appointment history cannot be deleted. Use merge for duplicates with history.</p>
      </div>
      <div class="cf-modal-footer">
        <button type="button" @click="patientDeleteOpen=false" class="cf-btn cf-btn-secondary"><i data-lucide="x-circle" class="h-4 w-4"></i>Cancel</button>
        <form method="post" action="{% url 'dashboard:delete_patient' patient.id %}" class="inline">
          {% csrf_token %}
          <button type="submit" class="cf-btn cf-btn-danger"><i data-lucide="trash-2" class="h-4 w-4"></i>Delete</button>
        </form>
      </div>
    </div>
  </div>
```

- [ ] **Step 10: Run patient backend and UI tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest patients/tests.py -k "patient_delete or merge" tests/test_design_system.py -k "patient_rows_have_guarded_delete_confirmation or patient_detail_has_guarded_delete_confirmation" -q
```

Expected: PASS.

- [ ] **Step 11: Commit patient delete changes only if commits are explicitly approved**

Run only after explicit commit approval:

```powershell
git add patients/tests.py dashboard/urls.py dashboard/views.py templates/dashboard/partials/patient_list.html templates/dashboard/partials/patient_row.html templates/dashboard/partials/patient_detail_content.html tests/test_design_system.py
git commit -m "feat: add guarded patient delete"
```

Expected: commit succeeds.

## Task 4: Final Verification And Regression Sweep

**Files:**
- Verify: `services/tests.py`
- Verify: `patients/tests.py`
- Verify: `dashboard/tests.py`
- Verify: `tests/test_design_system.py`
- Verify: Django project configuration

- [ ] **Step 1: Run domain test suites**

Run:

```powershell
.\env\Scripts\python.exe -m pytest services/tests.py patients/tests.py dashboard/tests.py -q
```

Expected: PASS.

- [ ] **Step 2: Run design-system tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py -q
```

Expected: PASS.

- [ ] **Step 3: Run Django checks**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Confirm no migration is needed**

Run:

```powershell
.\env\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 5: Inspect changed files before reporting completion**

Run:

```powershell
git diff -- dashboard/urls.py dashboard/views.py templates/dashboard/partials/service_row.html templates/dashboard/appointments.html templates/dashboard/partials/appointment_detail.html templates/dashboard/partials/patient_detail.html templates/dashboard/partials/patient_detail_content.html templates/dashboard/partials/patient_list.html templates/dashboard/partials/patient_row.html services/tests.py dashboard/tests.py patients/tests.py tests/test_design_system.py
```

Expected: diff contains only guarded delete functionality, tests, and template updates.

- [ ] **Step 6: Commit final verification only if commits are explicitly approved**

Run only after explicit commit approval and only if previous task commits were not already made:

```powershell
git add dashboard/urls.py dashboard/views.py templates/dashboard/partials/service_row.html templates/dashboard/appointments.html templates/dashboard/partials/appointment_detail.html templates/dashboard/partials/patient_detail.html templates/dashboard/partials/patient_detail_content.html templates/dashboard/partials/patient_list.html templates/dashboard/partials/patient_row.html services/tests.py dashboard/tests.py patients/tests.py tests/test_design_system.py docs/superpowers/specs/2026-06-04-guarded-delete-functionality-design.md docs/superpowers/plans/2026-06-04-guarded-delete-functionality-implementation-plan.md
git commit -m "feat: add guarded delete functionality"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: The plan covers guarded service deletion, appointment deletion from detail modal with calendar and patient-history HTMX behavior, guarded patient deletion, tenant scoping, POST-only endpoints, CSRF forms, no migrations, and regression tests.
- Placeholder scan: No placeholder markers or unspecified implementation sections remain.
- Type consistency: Routes, view names, event names, template IDs, and helper names are consistent across tests, implementation, and UI steps.
