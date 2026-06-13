import csv
import json
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_POST
from django.conf import settings as django_settings

from appointments.forms import AppointmentNoteForm, AppointmentStatusForm, StaffAppointmentForm
from appointments.models import Appointment
from clinics.ai_provider_validation import validate_ai_provider_base_url
from clinics.forms import (
    AIProviderSettingsForm,
    ClinicFAQForm,
    ClinicSettingsForm,
    SAVED_PROVIDER_SECRET_MASK,
    SharedAISettingsForm,
    WidgetSettingsForm,
)
from clinics.models import Clinic, ClinicAIProviderSettings, ClinicAISettings, ClinicMembership
from clinics.tenant import current_clinic, get_active_membership, user_can_manage_daily_ops, user_can_manage_settings
from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
from messenger.ai_provider_client import AIProviderError, fetch_available_models
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from scheduling.models import ClinicBusinessHour, UnavailableDate
from scheduling.utils import _date_is_unavailable, _inside_break, generate_slots, get_working_window, validate_slot
from patients.forms import PatientForm
from patients.models import Patient
from patients.utils import normalize_phone
from services.forms import ServiceForm
from accounts.forms import AppPasswordChangeForm
from yakap.forms import (
    AppointmentYakapStatusForm,
    ClinicYakapSettingsForm,
    PatientYakapProfileForm,
    ServiceYakapRuleForm,
    YakapCoverageCategoryForm,
    YakapExportForm,
    YakapLedgerEntryForm,
)
from yakap.models import (
    AppointmentYakapSnapshot,
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapAuditEvent,
    YakapCoverageCategory,
    YakapLedgerEntry,
)
from yakap.services import (
    YAKAP_LEDGER_SERVICE_RULE_ALLOWED_STATUSES,
    active_period_for_profile_category,
    balance_state_for,
    cancel_unposted_yakap_snapshot,
    create_yakap_audit_event,
    ensure_default_yakap_setup,
    estimated_remaining_for,
    ledger_entry_over_limit,
    patient_has_yakap_history,
    validate_yakap_ledger_posting,
    validate_yakap_appointment_cancellation,
    yakap_verification_freshness,
    yakap_profile_for_patient,
)


def _clinic_or_redirect(request, allow_missing=False):
    clinic = current_clinic(request)
    if not clinic:
        if allow_missing:
            return None
        raise PermissionDenied("No active clinic membership.")
    return clinic


def _embedded_iframe_url(request, clinic):
    return request.build_absolute_uri(reverse("widget:home", args=[clinic.slug])) + "?source=embed"


def _parse_required_time(value, label):
    parsed = parse_time(value or "")
    if parsed is None:
        raise ValidationError(f"{label} must be a valid time.")
    return parsed


def _validated_business_hour_rows(request):
    rows = []
    default_open = time(9, 0)
    default_close = time(17, 0)
    for weekday in range(7):
        is_open = request.POST.get(f"is_open_{weekday}") == "on"
        open_time_str = request.POST.get(f"open_time_{weekday}")
        close_time_str = request.POST.get(f"close_time_{weekday}")
        break_start_str = request.POST.get(f"break_start_{weekday}") or ""
        break_end_str = request.POST.get(f"break_end_{weekday}") or ""

        if is_open:
            open_time = _parse_required_time(open_time_str, "Open time")
            close_time = _parse_required_time(close_time_str, "Close time")
            if open_time >= close_time:
                raise ValidationError("Open time must be before close time.")
        else:
            open_time = parse_time(open_time_str or "") or default_open
            close_time = parse_time(close_time_str or "") or default_close

        break_start = parse_time(break_start_str) if break_start_str else None
        break_end = parse_time(break_end_str) if break_end_str else None
        if bool(break_start) != bool(break_end):
            raise ValidationError("Break start and end times must be provided together.")
        if break_start and break_end:
            if break_start >= break_end:
                raise ValidationError("Break start must be before break end.")
            if is_open and (break_start < open_time or break_end > close_time):
                raise ValidationError("Break times must be inside working hours.")

        rows.append(
            {
                "weekday": weekday,
                "is_open": is_open,
                "open_time": open_time,
                "close_time": close_time,
                "break_start": break_start,
                "break_end": break_end,
            }
        )
    return rows


def _redirect_with_appointment_error(request, message):
    if request.headers.get("HX-Request"):
        return HttpResponse(f'<p class="cf-error">{message}</p>')
    messages.error(request, message)
    return redirect("dashboard:appointments")


def _validation_error_message(exc):
    if hasattr(exc, "messages") and exc.messages:
        return exc.messages[0]
    return str(exc)


def _appointment_has_yakap_records(appointment):
    return hasattr(appointment, "yakap_snapshot") or appointment.yakap_ledger_entries.exists()


def _matched_patient_id_for_booking(clinic, phone):
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    patient = clinic.patients.filter(normalized_phone=normalized).order_by("created_at").first()
    return patient.id if patient else None


def _require_settings_permission(user):
    membership = get_active_membership(user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied


def _safe_csv_cell(value):
    value = "" if value is None else str(value)
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{value}"
    return value


def _parse_service_filter(value):
    if not value:
        return None
    try:
        service_id = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Invalid service filter.")
    if service_id < 1 or service_id > 9223372036854775807:
        raise ValidationError("Invalid service filter.")
    return service_id


def _clinic_day_bounds(clinic, date_value):
    clinic_tz = ZoneInfo(clinic.timezone)
    start = timezone.make_aware(datetime.combine(date_value, time.min), clinic_tz)
    end = start + timedelta(days=1)
    return start, end


def _apply_clinic_date_filters(qs, clinic, date_from, date_to):
    if date_from:
        parsed = parse_date(date_from)
        if not parsed:
            raise ValidationError("Invalid date filter.")
        start, _ = _clinic_day_bounds(clinic, parsed)
        qs = qs.filter(starts_at__gte=start)
    if date_to:
        parsed = parse_date(date_to)
        if not parsed:
            raise ValidationError("Invalid date filter.")
        _, end = _clinic_day_bounds(clinic, parsed)
        qs = qs.filter(starts_at__lt=end)
    return qs


def _appointment_htmx_response(request, clinic, appointment, message):
    modal_source = request.POST.get("modal_source", "")
    if modal_source == "calendar":
        response = HttpResponse("")
        response["HX-Trigger"] = _calendar_modal_trigger(message, close=True)
        return response
    if modal_source == "patient":
        patient = get_object_or_404(
            clinic.patients.prefetch_related("appointments__service"),
            pk=appointment.patient_id,
        )
        response = render(
            request,
            "dashboard/partials/patient_detail_content.html",
            _patient_detail_context(clinic, patient, membership=get_active_membership(request.user)),
        )
        response["HX-Retarget"] = "#patient-detail-content"
        response["HX-Reswap"] = "innerHTML"
    elif modal_source == "yakap":
        response = HttpResponse("")
        response["HX-Refresh"] = "true"
    else:
        response = render(request, "dashboard/partials/appointment_list.html", _appointments_context(request, clinic))
        response["HX-Retarget"] = "#appointments-table"
        response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = json.dumps({
        "appointmentSaved": True,
        "toast-message": {"message": message, "type": "success"},
    })
    return response


def _service_yakap_rule_instance(service):
    if service is None:
        return None
    try:
        return service.yakap_rule
    except ServiceYakapRule.DoesNotExist:
        return None


def _service_yakap_rule_form(clinic, service=None, data=None):
    return ServiceYakapRuleForm(
        clinic,
        data=data,
        instance=_service_yakap_rule_instance(service),
        prefix="yakap",
    )


def _service_yakap_rule_data_submitted(data):
    return bool(data) and any(key.startswith("yakap_") for key in data)


def _save_service_yakap_rule(clinic, service, data, *, actor=None):
    form = _service_yakap_rule_form(clinic, service, data)
    if not form.is_valid():
        return form
    rule = form.save(commit=False)
    rule.clinic = clinic
    rule.service = service
    rule.save()
    if actor:
        create_yakap_audit_event(
            clinic=clinic,
            actor=actor,
            action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
            obj=rule,
            summary=f"YAKAP service rule updated for {service.name}.",
        )
    return form


def _calendar_modal_trigger(message, *, close=False, refetch=True):
    trigger = {"toast-message": {"message": message, "type": "success"}}
    if refetch:
        trigger["calendar-refetch"] = True
    if close:
        trigger["close-calendar-modal"] = True
    return json.dumps(trigger)


def _request_filter_params(request):
    if request.method == "POST" and request.headers.get("HX-Request"):
        params = request.POST.copy()
        current_url = request.headers.get("HX-Current-URL")
        if current_url:
            current_params = QueryDict(urlparse(current_url).query)
            for key in current_params:
                if key == "service":
                    try:
                        _parse_service_filter(current_params.get(key))
                    except ValidationError:
                        continue
                if key not in params:
                    params.setlist(key, current_params.getlist(key))
        return params
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
    qs = _apply_clinic_date_filters(qs, clinic, date_from, date_to)
    service_filter = params.get("service")
    if service_filter:
        qs = qs.filter(service_id=_parse_service_filter(service_filter))
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


def _yakap_ledger_blockers(clinic, appointment, snapshot, profile, freshness):
    blockers = []
    if appointment.status not in {Appointment.STATUS_CONFIRMED, Appointment.STATUS_COMPLETED}:
        blockers.append("Confirm or complete the appointment before posting YAKAP usage.")
    if not snapshot or snapshot.coverage_status not in {
        AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT,
        AppointmentYakapSnapshot.STATUS_POSTED,
    }:
        blockers.append("Mark the visit as verified for this visit before posting usage.")
    if profile is None or profile.status != PatientYakapProfile.STATUS_ACTIVE:
        blockers.append("Set the patient YAKAP profile to active after clinic verification.")
    rule = getattr(appointment.service, "yakap_rule", None)
    if not rule or not rule.category_id or not rule.category.is_active:
        blockers.append("Configure an active YAKAP category for this service.")
    elif rule.coverage_status not in YAKAP_LEDGER_SERVICE_RULE_ALLOWED_STATUSES:
        blockers.append("Configure this service as YAKAP-covered before posting usage.")
    return blockers


def _appointment_detail_context(
    clinic,
    appointment,
    *,
    init_mode="detail",
    source="",
    status_form=None,
    note_form=None,
    yakap_status_form=None,
    yakap_ledger_form=None,
    can_manage_daily_ops=False,
    membership=None,
):
    try:
        yakap_snapshot = appointment.yakap_snapshot
    except AppointmentYakapSnapshot.DoesNotExist:
        yakap_snapshot = None
    try:
        yakap_profile = appointment.patient.yakap_profile
    except Patient.yakap_profile.RelatedObjectDoesNotExist:
        yakap_profile = None
    try:
        yakap_settings = clinic.yakap_settings
    except ClinicYakapSettings.DoesNotExist:
        yakap_settings = None
    yakap_freshness = yakap_verification_freshness(yakap_profile, settings=yakap_settings)
    yakap_ledger_blockers = _yakap_ledger_blockers(clinic, appointment, yakap_snapshot, yakap_profile, yakap_freshness)
    can_manage_yakap_settings = user_can_manage_settings(membership) if membership else False
    if yakap_status_form is None:
        yakap_status_form = (
            AppointmentYakapStatusForm(instance=yakap_snapshot)
            if yakap_snapshot
            else AppointmentYakapStatusForm()
        )
    yakap_rule = getattr(appointment.service, "yakap_rule", None)

    return {
        "clinic": clinic,
        "appointment": appointment,
        "status_form": status_form if status_form is not None else AppointmentStatusForm(instance=appointment),
        "note_form": note_form if note_form is not None else AppointmentNoteForm(),
        "init_mode": init_mode,
        "source": source,
        "yakap_snapshot": yakap_snapshot,
        "yakap_status_form": yakap_status_form,
        "yakap_verification_freshness": yakap_freshness,
        "yakap_ledger_blockers": yakap_ledger_blockers,
        "yakap_can_post_ledger": not yakap_ledger_blockers,
        "can_manage_yakap_settings": can_manage_yakap_settings,
        "yakap_ledger_form": yakap_ledger_form if yakap_ledger_form is not None else YakapLedgerEntryForm(
            clinic,
            patient=appointment.patient,
            category=getattr(yakap_rule, "category", None),
            allow_privileged_entries=can_manage_yakap_settings,
        ),
        "can_manage_daily_ops": can_manage_daily_ops,
    }


def _patient_detail_context(clinic, patient, *, membership=None):
    appointments = clinic.appointments.filter(patient=patient)
    try:
        yakap_profile = patient.yakap_profile
    except Patient.yakap_profile.RelatedObjectDoesNotExist:
        yakap_profile = None

    yakap_balances = []
    yakap_ledger_entries = []
    if yakap_profile:
        for category in clinic.yakap_categories.filter(is_active=True):
            balance = estimated_remaining_for(yakap_profile, category, create_period=False)
            yakap_balances.append({"category": category, **balance})
        yakap_ledger_entries = clinic.yakap_ledger_entries.filter(patient=patient).select_related(
            "category",
            "appointment",
            "service",
        )[:5]
    yakap_profile_form_instance = yakap_profile or PatientYakapProfile(clinic=clinic, patient=patient)

    return {
        "clinic": clinic,
        "patient": patient,
        "kpi_total": appointments.count(),
        "kpi_upcoming": appointments.filter(status__in=["pending", "confirmed"], starts_at__gte=timezone.now()).count(),
        "kpi_completed": appointments.filter(status="completed").count(),
        "kpi_cancelled": appointments.filter(status__in=["cancelled", "no_show"]).count(),
        "last_appointment": appointments.order_by("starts_at").last(),
        "yakap_profile": yakap_profile,
        "yakap_profile_form": PatientYakapProfileForm(instance=yakap_profile_form_instance),
        "yakap_balances": yakap_balances,
        "yakap_ledger_entries": yakap_ledger_entries,
        "can_manage_daily_ops": user_can_manage_daily_ops(membership) if membership else False,
    }


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


@login_required
def home(request):
    clinic = _clinic_or_redirect(request, allow_missing=True)
    if not clinic:
        return redirect("accounts:signup")
    clinic_tz = ZoneInfo(clinic.timezone)
    today = timezone.localdate(timezone.now(), clinic_tz)
    day_start = datetime.combine(today, time.min, clinic_tz)
    day_end = day_start + timedelta(days=1)
    appointments = clinic.appointments.select_related("patient", "service").filter(starts_at__gte=day_start, starts_at__lt=day_end)
    pending_appointments = clinic.appointments.select_related("patient", "service").filter(status=Appointment.STATUS_PENDING)
    upcoming = clinic.appointments.select_related("patient", "service").filter(starts_at__gte=timezone.now()).exclude(status=Appointment.STATUS_CANCELLED)[:5]
    slot_service = clinic.services.filter(is_active=True, is_archived=False).first()
    open_slots = generate_slots(clinic, slot_service, today) if slot_service else []
    metrics = {
        "today": appointments.count(),
        "pending": pending_appointments.count(),
        "upcoming": clinic.appointments.filter(starts_at__gte=timezone.now()).exclude(status=Appointment.STATUS_CANCELLED).count(),
        "patients": clinic.patients.count(),
        "cancelled": clinic.appointments.filter(status=Appointment.STATUS_CANCELLED).count(),
        "completed": clinic.appointments.filter(status=Appointment.STATUS_COMPLETED).count(),
        "no_show": appointments.filter(status=Appointment.STATUS_NO_SHOW).count(),
    }
    context = {
        "clinic": clinic,
        "appointments": appointments,
        "upcoming": upcoming,
        "metrics": metrics,
        "today": today,
        "open_slots_count": len(open_slots),
        "next_slot_label": open_slots[0]["label"] if open_slots else "",
        "slot_service": slot_service,
    }
    with timezone.override(clinic_tz):
        return render(request, "dashboard/home.html", context)


@login_required
def calendar(request):
    clinic = _clinic_or_redirect(request, allow_missing=True)
    if not clinic:
        return redirect("accounts:signup")
    return render(request, "dashboard/calendar.html", {"clinic": clinic, "status_choices": Appointment.STATUS_CHOICES})


@login_required
def calendar_events(request):
    clinic = _clinic_or_redirect(request, allow_missing=True)
    if not clinic:
        return JsonResponse({"error": "No clinic context."}, status=400)
    events = []
    qs = clinic.appointments.select_related("patient", "service").all()

    # Date range filtering based on FullCalendar fetchInfo
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start and end:
        from django.utils.dateparse import parse_datetime
        start_dt = parse_datetime(start)
        end_dt = parse_datetime(end)
        if start_dt and end_dt:
            qs = qs.filter(starts_at__gte=start_dt, starts_at__lt=end_dt)

    service = request.GET.get("service")
    if service:
        try:
            service_id = int(service)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid service filter."}, status=400)
        _, max_service_id = connection.ops.integer_field_range("BigAutoField")
        if service_id < 1 or (max_service_id is not None and service_id > max_service_id):
            return JsonResponse({"error": "Invalid service filter."}, status=400)
        qs = qs.filter(service_id=service_id)

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    color_map = {
        Appointment.STATUS_PENDING: {"backgroundColor": "#fff6e7", "borderColor": "#80531f", "textColor": "#80531f"},
        Appointment.STATUS_CONFIRMED: {"backgroundColor": "#ecfeff", "borderColor": "#06b6d4", "textColor": "#0e7490"},
        Appointment.STATUS_COMPLETED: {"backgroundColor": "#e9f7ef", "borderColor": "#0f766e", "textColor": "#0f766e"},
        Appointment.STATUS_CANCELLED: {"backgroundColor": "#fde8ef", "borderColor": "#ea2261", "textColor": "#b3194a"},
        Appointment.STATUS_NO_SHOW: {"backgroundColor": "#edf2f7", "borderColor": "#4a5870", "textColor": "#4a5870"},
    }

    clinic_tz = ZoneInfo(clinic.timezone)
    for appointment in qs:
        colors = color_map.get(appointment.status, {})
        local_start = timezone.localtime(appointment.starts_at, clinic_tz)
        local_end = timezone.localtime(appointment.ends_at, clinic_tz)
        starts_at_label = local_start.strftime("%I:%M %p").lstrip("0").lower()
        is_reschedulable = appointment.status not in {
            Appointment.STATUS_COMPLETED,
            Appointment.STATUS_CANCELLED,
        }
        events.append(
            {
                "id": appointment.id,
                "title": f"{starts_at_label} {appointment.patient.full_name}",
                "start": local_start.isoformat(),
                "end": local_end.isoformat(),
                "className": f"status-{appointment.status}",
                "editable": is_reschedulable,
                "extendedProps": {"status": appointment.status},
                "url": f"{reverse('dashboard:appointment_detail', args=[appointment.id])}?source=calendar",
                **colors,
            }
        )
    return JsonResponse(events, safe=False)


@login_required
@require_POST
def calendar_reschedule(request):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return JsonResponse({"success": False, "error": "No clinic context."}, status=400)

    appointment_id = request.POST.get("appointment_id")
    if not appointment_id:
        return JsonResponse({"success": False, "error": "Appointment ID required."}, status=400)

    new_start_str = request.POST.get("starts_at")

    try:
        appointment = clinic.appointments.select_related("service").get(pk=appointment_id)
    except (Appointment.DoesNotExist, ValueError):
        return JsonResponse({"success": False, "error": "Appointment not found."}, status=404)

    # Permission check
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied

    # Prevent rescheduling completed or cancelled appointments
    if appointment.status in {Appointment.STATUS_COMPLETED, Appointment.STATUS_CANCELLED}:
        return JsonResponse({"success": False, "error": "Cannot reschedule a completed or cancelled appointment."})

    new_start = parse_datetime(new_start_str)
    if not new_start:
        return JsonResponse({"success": False, "error": "Invalid date/time format."})

    # Normalize to clinic timezone so working-hour comparisons are correct
    tz = ZoneInfo(clinic.timezone)
    if timezone.is_aware(new_start):
        new_start = new_start.astimezone(tz)
    else:
        new_start = timezone.make_aware(new_start, tz)

    # Prevent rescheduling to the past
    if new_start < timezone.now():
        return JsonResponse({"success": False, "error": "Cannot reschedule to the past."})

    duration = appointment.service.effective_duration()
    if duration is None:
        return JsonResponse({"success": False, "error": "Service duration is not set."})
    new_end = new_start + timedelta(minutes=duration)

    date_value = new_start.date()

    if _date_is_unavailable(clinic, date_value):
        return JsonResponse({"success": False, "error": "Clinic is not available on this day."})

    window = get_working_window(clinic, date_value)
    if not window:
        return JsonResponse({"success": False, "error": "Clinic is not open on this day."})

    open_time, close_time, break_start, break_end = window
    if new_start.time() < open_time or new_end.time() > close_time:
        return JsonResponse({"success": False, "error": "Appointment is outside working hours."})

    if _inside_break(new_start.time(), new_end.time(), break_start, break_end):
        return JsonResponse({"success": False, "error": "Appointment overlaps with a break."})

    with transaction.atomic():
        Clinic.objects.select_for_update().get(pk=clinic.pk)
        overlaps = Appointment.objects.filter(
            clinic=clinic,
            starts_at__lt=new_end,
            ends_at__gt=new_start,
        ).exclude(status=Appointment.STATUS_CANCELLED).exclude(pk=appointment.pk)
        if overlaps.exists():
            return JsonResponse({"success": False, "error": "This clinic already has an appointment at that time."})

        appointment.starts_at = new_start
        appointment.ends_at = new_end
        try:
            appointment.save()
        except ValidationError as e:
            return JsonResponse({"success": False, "error": str(e)})
    return JsonResponse({"success": True})


@login_required
def appointments(request):
    clinic = _clinic_or_redirect(request)
    try:
        context = _appointments_context(request, clinic)
    except ValidationError as error:
        return HttpResponse(error.messages[0], status=400)
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/appointment_list.html", context)
    return render(request, "dashboard/appointments.html", context)


@login_required
@require_POST
def create_appointment(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    with transaction.atomic():
        clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        form = StaffAppointmentForm(clinic, request.POST)
        if form.is_valid():
            patient, _ = Patient.find_or_create_for_booking(
                clinic=clinic,
                full_name=form.cleaned_data["patient_name"],
                phone=form.cleaned_data["patient_phone"],
                email=form.cleaned_data["patient_email"],
            )
            appointment = form.save(commit=False)
            appointment.clinic = clinic
            appointment.patient = patient
            appointment.save()
            messages.success(request, "Appointment created.")
        else:
            messages.error(request, form.errors.as_text())
    return redirect("dashboard:appointments")


@login_required
def appointment_detail(request, pk):
    clinic = _clinic_or_redirect(request)
    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    membership = get_active_membership(request.user)
    can_manage_daily_ops = user_can_manage_daily_ops(membership)
    init_mode = request.GET.get("mode", "detail")
    if init_mode not in {"detail", "cancel", "reschedule", "delete"}:
        init_mode = "detail"
    if not can_manage_daily_ops and init_mode != "detail":
        init_mode = "detail"
    return render(
        request,
        "dashboard/partials/appointment_detail.html",
        _appointment_detail_context(
            clinic,
            appointment,
            init_mode=init_mode,
            source=request.GET.get("source", ""),
            can_manage_daily_ops=can_manage_daily_ops,
            membership=membership,
        ),
    )


@login_required
def appointment_edit(request, pk):
    clinic = _clinic_or_redirect(request)
    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if request.method == "POST":
        saved = False
        form = None
        try:
            with transaction.atomic():
                clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
                appointment = get_object_or_404(
                    clinic.appointments.select_for_update().select_related("patient", "service"),
                    pk=pk,
                )
                existing_patient_id = appointment.patient_id
                existing_service_id = appointment.service_id
                existing_status = appointment.status
                form = StaffAppointmentForm(clinic, request.POST, instance=appointment)
                if form.is_valid():
                    edited_appointment = form.save(commit=False)
                    yakap_records_exist = _appointment_has_yakap_records(appointment)
                    service_changed = edited_appointment.service_id != existing_service_id
                    matched_patient_id = _matched_patient_id_for_booking(clinic, form.cleaned_data["patient_phone"])
                    patient_changed = matched_patient_id != existing_patient_id
                    if yakap_records_exist and (patient_changed or service_changed):
                        form.add_error(None, "Cancel the YAKAP request or create a new appointment before changing patient or service.")
                    else:
                        cancelling = edited_appointment.status == Appointment.STATUS_CANCELLED and existing_status != Appointment.STATUS_CANCELLED
                        if cancelling:
                            validate_yakap_appointment_cancellation(appointment)
                        patient, _ = Patient.find_or_create_for_booking(
                            clinic=clinic,
                            full_name=form.cleaned_data["patient_name"],
                            phone=form.cleaned_data["patient_phone"],
                            email=form.cleaned_data["patient_email"],
                        )
                        edited_appointment.patient = patient
                        edited_appointment.save()
                        if cancelling:
                            cancel_unposted_yakap_snapshot(edited_appointment, actor=request.user)
                        appointment = edited_appointment
                        saved = True
        except ValidationError as exc:
            if form is None:
                form = StaffAppointmentForm(clinic, request.POST, instance=appointment)
            form.add_error(None, _validation_error_message(exc))
            appointment.refresh_from_db()
        if not saved:
            if request.headers.get("HX-Request"):
                return render(request, "dashboard/partials/appointment_form.html", {
                    "form": form,
                    "appointment": appointment,
                    "patient_form": PatientForm(clinic=clinic),
                    "source": request.POST.get("modal_source", ""),
                })
            messages.error(request, form.errors.as_text())
            return redirect("dashboard:appointments")
        if saved:
            if request.headers.get("HX-Request"):
                if request.POST.get("modal_source") == "calendar":
                    response = render(
                        request,
                        "dashboard/partials/appointment_detail.html",
                        _appointment_detail_context(
                            clinic,
                            appointment,
                            source="calendar",
                            can_manage_daily_ops=True,
                            membership=membership,
                        ),
                    )
                    response["HX-Trigger"] = _calendar_modal_trigger("Appointment updated.")
                    return response
                response = render(request, "dashboard/partials/appointment_row.html", {"appointment": appointment})
                response["HX-Retarget"] = f"#appointment-row-{appointment.id}"
                response["HX-Reswap"] = "outerHTML"
                response["HX-Trigger"] = json.dumps({
                    "appointmentSaved": True,
                    "toast-message": {"message": "Appointment updated.", "type": "success"}
                })
                return response
            messages.success(request, "Appointment updated.")
            return redirect("dashboard:appointments")
    else:
        form = StaffAppointmentForm(clinic, instance=appointment)
        if request.headers.get("HX-Request"):
            return render(request, "dashboard/partials/appointment_form.html", {
                "form": form,
                "appointment": appointment,
                "patient_form": PatientForm(clinic=clinic),
                "source": request.GET.get("source", ""),
            })
        return redirect("dashboard:appointments")


@login_required
@require_POST
def appointment_cancel(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    try:
        with transaction.atomic():
            appointment = get_object_or_404(
                clinic.appointments.select_for_update().select_related("patient", "service"),
                pk=pk,
            )
            if not appointment.can_transition_to(Appointment.STATUS_CANCELLED):
                return _redirect_with_appointment_error(request, "Cannot cancel this appointment from its current status.")
            validate_yakap_appointment_cancellation(appointment)
            reason = request.POST.get("cancellation_reason", "")
            appointment.status = Appointment.STATUS_CANCELLED
            appointment.cancellation_reason = reason
            appointment.save()
            cancel_unposted_yakap_snapshot(appointment, actor=request.user)
    except ValidationError as exc:
        return _redirect_with_appointment_error(request, _validation_error_message(exc))
    if request.headers.get("HX-Request"):
        return _appointment_htmx_response(request, clinic, appointment, "Appointment cancelled.")
    messages.success(request, "Appointment cancelled.")
    return redirect("dashboard:appointments")


@login_required
@require_POST
def delete_appointment(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    with transaction.atomic():
        appointment = get_object_or_404(clinic.appointments.select_for_update().select_related("patient"), pk=pk)
        patient_id = appointment.patient_id
        if appointment.yakap_ledger_entries.exists() or hasattr(appointment, "yakap_snapshot"):
            return _redirect_with_appointment_error(request, "Cancel the appointment or reconcile YAKAP records before deleting it.")
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
                _patient_detail_context(clinic, patient, membership=get_active_membership(request.user)),
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


@login_required
@require_POST
def appointment_reschedule(request, pk):
    clinic = _clinic_or_redirect(request)
    appointment = get_object_or_404(clinic.appointments.select_related("service"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if appointment.status in {Appointment.STATUS_COMPLETED, Appointment.STATUS_CANCELLED}:
        return _redirect_with_appointment_error(request, "Cannot reschedule a completed or cancelled appointment.")
    new_date_str = request.POST.get("new_date")
    new_time_str = request.POST.get("new_time")
    if not new_date_str or not new_time_str:
        msg = "Date and time are required."
        if request.headers.get("HX-Request"):
            return HttpResponse(f'<p class="text-sm text-rose-600">{msg}</p>')
        messages.error(request, msg)
        return redirect("dashboard:appointments")
    tz = ZoneInfo(clinic.timezone)
    try:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()
        new_time = datetime.strptime(new_time_str, "%H:%M").time()
        new_starts_at = timezone.make_aware(datetime.combine(new_date, new_time), tz)
        new_ends_at = new_starts_at + timedelta(minutes=appointment.service.effective_duration())
    except ValueError:
        msg = "Invalid date or time format."
        if request.headers.get("HX-Request"):
            return HttpResponse(f'<p class="text-sm text-rose-600">{msg}</p>')
        messages.error(request, msg)
        return redirect("dashboard:appointments")
    with transaction.atomic():
        Clinic.objects.select_for_update().get(pk=clinic.pk)
        try:
            validate_slot(clinic, new_starts_at, new_ends_at, exclude_appointment=appointment)
        except ValidationError as e:
            msg = str(e)
            if request.headers.get("HX-Request"):
                return HttpResponse(f'<p class="text-sm text-rose-600">{msg}</p>')
            messages.error(request, msg)
            return redirect("dashboard:appointments")
        appointment.starts_at = new_starts_at
        appointment.ends_at = new_ends_at
        appointment.save()
    if request.headers.get("HX-Request"):
        return _appointment_htmx_response(request, clinic, appointment, "Appointment rescheduled.")
    messages.success(request, "Appointment rescheduled.")
    return redirect("dashboard:appointments")


@login_required
def export_csv(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    qs = clinic.appointments.select_related("patient", "service").all()
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    try:
        qs = _apply_clinic_date_filters(qs, clinic, date_from, date_to)
    except ValidationError as error:
        return HttpResponse(error.messages[0], status=400)
    service_filter = request.GET.get("service")
    if service_filter:
        try:
            qs = qs.filter(service_id=_parse_service_filter(service_filter))
        except ValidationError as error:
            return HttpResponse(error.messages[0], status=400)
    source_filter = request.GET.get("source")
    if source_filter:
        qs = qs.filter(source=source_filter)
    payment_filter = request.GET.get("payment_state")
    if payment_filter:
        qs = qs.filter(payment_state=payment_filter)
    import csv
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="appointments.csv"'
    writer = csv.writer(response)
    writer.writerow(["ID", "Patient Name", "Phone", "Service", "Date", "Time", "Status", "Source", "Payment State", "Created At"])
    clinic_tz = ZoneInfo(clinic.timezone)
    for appt in qs:
        local_start = timezone.localtime(appt.starts_at, clinic_tz)
        local_created = timezone.localtime(appt.created_at, clinic_tz)
        writer.writerow([
            appt.id,
            _safe_csv_cell(appt.patient.full_name),
            _safe_csv_cell(appt.patient.phone),
            _safe_csv_cell(appt.service.name),
            local_start.strftime("%Y-%m-%d"),
            local_start.strftime("%H:%M"),
            _safe_csv_cell(appt.get_status_display()),
            _safe_csv_cell(appt.get_source_display()),
            _safe_csv_cell(appt.get_payment_state_display()),
            local_created.strftime("%Y-%m-%d %H:%M"),
        ])
    return response


@login_required
@require_POST
def update_appointment(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    form = None
    updated = False
    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    try:
        with transaction.atomic():
            appointment = get_object_or_404(
                clinic.appointments.select_for_update().select_related("patient", "service"),
                pk=pk,
            )
            existing_status = appointment.status
            form = AppointmentStatusForm(request.POST, instance=appointment)
            updated = form.is_valid()
            if updated:
                cancelling = form.cleaned_data["status"] == Appointment.STATUS_CANCELLED and existing_status != Appointment.STATUS_CANCELLED
                if cancelling:
                    validate_yakap_appointment_cancellation(appointment)
                appointment = form.save()
                if cancelling:
                    cancel_unposted_yakap_snapshot(appointment, actor=request.user)
                messages.success(request, "Appointment updated.")
    except ValidationError as exc:
        if form is None:
            form = AppointmentStatusForm(request.POST, instance=appointment)
        form.add_error("status", _validation_error_message(exc))
        updated = False
        appointment.refresh_from_db()
    if not updated:
        appointment.refresh_from_db()
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "dashboard/partials/appointment_detail.html",
            _appointment_detail_context(
                clinic,
                appointment,
                status_form=AppointmentStatusForm(instance=appointment) if updated else form,
                source=request.POST.get("modal_source", ""),
                can_manage_daily_ops=True,
                membership=membership,
            ),
        )
        if not updated:
            return response
        if request.POST.get("modal_source") == "calendar":
            response["HX-Trigger"] = _calendar_modal_trigger("Appointment updated.")
        else:
            response["HX-Trigger"] = json.dumps({
                "toast-message": {"message": "Appointment updated.", "type": "success"}
            })
        return response
    return redirect("dashboard:appointments")


@login_required
@require_POST
def add_appointment_note(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    form = AppointmentNoteForm(request.POST)
    added = form.is_valid()
    if added:
        note = form.save(commit=False)
        note.appointment = appointment
        note.author = request.user
        note.save()
        messages.success(request, "Note added.")
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "dashboard/partials/appointment_detail.html",
            _appointment_detail_context(
                clinic,
                appointment,
                note_form=AppointmentNoteForm() if added else form,
                source=request.POST.get("modal_source", ""),
                can_manage_daily_ops=True,
                membership=membership,
            ),
        )
        if not added:
            return response
        if request.POST.get("modal_source") == "calendar":
            response["HX-Trigger"] = _calendar_modal_trigger("Note added.", refetch=False)
        else:
            response["HX-Trigger"] = json.dumps({
                "toast-message": {"message": "Note added.", "type": "success"}
            })
        return response
    return redirect("dashboard:appointments")


@login_required
@require_POST
def update_appointment_yakap_status(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied

    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    try:
        snapshot = appointment.yakap_snapshot
    except AppointmentYakapSnapshot.DoesNotExist:
        snapshot = AppointmentYakapSnapshot(
            clinic=clinic,
            requested=True,
            coverage_status=AppointmentYakapSnapshot.STATUS_NEEDS_VERIFICATION,
        )

    form = AppointmentYakapStatusForm(request.POST, instance=snapshot)
    saved = form.is_valid()
    if saved:
        snapshot = form.save(commit=False)
        snapshot.clinic = clinic
        snapshot.appointment = appointment
        snapshot.requested = snapshot.coverage_status != AppointmentYakapSnapshot.STATUS_NOT_REQUESTED
        if snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT:
            snapshot.verified_at = timezone.now()
            snapshot.verified_by = request.user
        else:
            snapshot.verified_at = None
            snapshot.verified_by = None
        snapshot.save()
        create_yakap_audit_event(
            clinic=clinic,
            actor=request.user,
            action=YakapAuditEvent.ACTION_APPOINTMENT_STATUS_CHANGED,
            obj=snapshot,
            summary=f"Updated appointment YAKAP status to {snapshot.get_coverage_status_display()}.",
        )
        messages.success(request, "YAKAP appointment status updated.")
    else:
        messages.error(request, form.errors.as_text())

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "dashboard/partials/appointment_detail.html",
            _appointment_detail_context(
                clinic,
                appointment,
                source=request.POST.get("modal_source", ""),
                yakap_status_form=AppointmentYakapStatusForm(instance=snapshot) if saved else form,
                can_manage_daily_ops=True,
                membership=membership,
            ),
        )
        if not saved:
            return response
        if request.POST.get("modal_source") == "calendar":
            response["HX-Trigger"] = _calendar_modal_trigger("YAKAP appointment status updated.", refetch=False)
        else:
            response["HX-Trigger"] = json.dumps({
                "toast-message": {"message": "YAKAP appointment status updated.", "type": "success"}
            })
        return response

    return redirect("dashboard:appointments")


@login_required
@require_POST
def appointment_yakap_ledger(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    can_manage_yakap_settings = user_can_manage_settings(membership)

    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    privileged_entry_types = {YakapLedgerEntry.TYPE_ADJUSTMENT, YakapLedgerEntry.TYPE_REVERSAL}
    if request.POST.get("entry_type") in privileged_entry_types and not can_manage_yakap_settings:
        raise PermissionDenied
    if request.POST.get("reversal_of") and not can_manage_yakap_settings:
        raise PermissionDenied
    submitted_category = None
    try:
        submitted_category = clinic.yakap_categories.filter(is_active=True, pk=request.POST.get("category")).first()
    except (TypeError, ValueError):
        submitted_category = None
    form = YakapLedgerEntryForm(
        clinic,
        request.POST,
        patient=appointment.patient,
        category=submitted_category,
        allow_privileged_entries=can_manage_yakap_settings,
    )
    saved = form.is_valid()
    if saved:
        entry = form.save(commit=False)
        entry.clinic = clinic
        entry.patient = appointment.patient
        entry.appointment = appointment
        entry.service = appointment.service
        entry.created_by = request.user
        if entry.verification_status == YakapLedgerEntry.VERIFICATION_VERIFIED:
            entry.verified_at = timezone.now()
            entry.verified_by = request.user
        try:
            with transaction.atomic():
                appointment = get_object_or_404(
                    clinic.appointments.select_for_update().select_related("patient", "service"),
                    pk=appointment.pk,
                )
                locked_patient = clinic.patients.select_for_update().get(pk=appointment.patient_id)
                try:
                    profile = locked_patient.yakap_profile
                except Patient.yakap_profile.RelatedObjectDoesNotExist:
                    profile = None
                entry.patient = locked_patient
                entry.appointment = appointment
                entry.service = appointment.service
                entry.profile = profile
                try:
                    settings_obj = clinic.yakap_settings
                except ClinicYakapSettings.DoesNotExist:
                    settings_obj = None
                confirm_stale_verification = request.POST.get("confirm_stale_verification") == "on"
                verification_freshness = yakap_verification_freshness(profile, settings=settings_obj)
                validate_yakap_ledger_posting(
                    entry,
                    appointment,
                    profile,
                    settings=settings_obj,
                    confirm_stale_verification=confirm_stale_verification,
                )
                is_over_limit, _remaining_after_entry = ledger_entry_over_limit(entry, create_period=False)
                if is_over_limit:
                    try:
                        hard_block_exceeded = clinic.yakap_settings.hard_block_exceeded
                    except ClinicYakapSettings.DoesNotExist:
                        hard_block_exceeded = False
                    if hard_block_exceeded:
                        saved = False
                        form.add_error(
                            None,
                            "This YAKAP usage is blocked by clinic YAKAP settings because it exceeds estimated remaining coverage.",
                        )
                    elif request.POST.get("confirm_over_limit") != "on":
                        saved = False
                        form.add_error(
                            None,
                            "This YAKAP usage exceeds estimated remaining coverage. Confirm over-limit posting to continue.",
                        )
                if saved:
                    entry.profile = profile
                    if confirm_stale_verification and verification_freshness["is_stale"]:
                        profile.last_verified_at = timezone.now()
                        profile.last_verified_by = request.user
                        profile.save(update_fields=["last_verified_at", "last_verified_by", "updated_at"])
                    entry.full_clean()
                    period = active_period_for_profile_category(profile, entry.category, when=entry.occurred_at)
                    profile.credit_line_periods.select_for_update().get(pk=period.pk)
                    entry.save()
                    create_yakap_audit_event(
                        clinic=clinic,
                        actor=request.user,
                        action=(
                            YakapAuditEvent.ACTION_LEDGER_REVERSED
                            if entry.entry_type == YakapLedgerEntry.TYPE_REVERSAL
                            else YakapAuditEvent.ACTION_LEDGER_POSTED
                        ),
                        obj=entry,
                        summary=f"Posted {entry.get_entry_type_display()} of {entry.amount} for {entry.category.name}.",
                    )
                    if hasattr(appointment, "yakap_snapshot"):
                        snapshot = appointment.yakap_snapshot
                        if snapshot.requested and snapshot.coverage_status == AppointmentYakapSnapshot.STATUS_VERIFIED_FOR_VISIT:
                            snapshot.coverage_status = AppointmentYakapSnapshot.STATUS_POSTED
                            snapshot.full_clean()
                            snapshot.save(update_fields=["coverage_status", "updated_at"])
        except ValidationError as exc:
            saved = False
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    target = field if field in form.fields else None
                    for error in errors:
                        form.add_error(target, error)
            else:
                for error in exc.messages:
                    form.add_error(None, error)
            messages.error(request, form.errors.as_text())
        else:
            if saved:
                messages.success(request, "YAKAP usage added.")
            else:
                messages.error(request, form.errors.as_text())
    else:
        messages.error(request, form.errors.as_text())

    if request.headers.get("HX-Request"):
        response = render(
            request,
            "dashboard/partials/appointment_detail.html",
            _appointment_detail_context(
                clinic,
                appointment,
                source=request.POST.get("modal_source", ""),
                yakap_ledger_form=(
                    YakapLedgerEntryForm(
                        clinic,
                        patient=appointment.patient,
                        category=getattr(getattr(appointment.service, "yakap_rule", None), "category", None),
                        allow_privileged_entries=can_manage_yakap_settings,
                    )
                    if saved
                    else form
                ),
                can_manage_daily_ops=True,
                membership=membership,
            ),
        )
        if not saved:
            return response
        if request.POST.get("modal_source") == "calendar":
            response["HX-Trigger"] = _calendar_modal_trigger("YAKAP usage added.", refetch=False)
        else:
            response["HX-Trigger"] = json.dumps({
                "toast-message": {"message": "YAKAP usage added.", "type": "success"}
            })
        return response

    return redirect("dashboard:appointments")


@login_required
def patients(request):
    clinic = _clinic_or_redirect(request)
    context = _patients_context(request, clinic)
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/patient_list.html", context)
    return render(request, "dashboard/patients.html", context)


@login_required
@require_POST
def create_patient(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    form = PatientForm(clinic=clinic, data=request.POST)
    if form.is_valid():
        patient = form.save(commit=False)
        patient.clinic = clinic
        patient.save()
        messages.success(request, "Patient saved.")
    return redirect("dashboard:patients")


@login_required
def patient_detail(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    patient = get_object_or_404(
        clinic.patients.prefetch_related(
            "appointments__service",
        ),
        pk=pk,
    )
    context = _patient_detail_context(clinic, patient, membership=membership)
    return render(request, "dashboard/partials/patient_detail.html", context)


@login_required
@require_POST
def update_patient_yakap_profile(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied

    patient = get_object_or_404(clinic.patients, pk=pk)
    try:
        profile = patient.yakap_profile
    except Patient.yakap_profile.RelatedObjectDoesNotExist:
        profile = PatientYakapProfile(clinic=clinic, patient=patient)
    form = PatientYakapProfileForm(request.POST, instance=profile)
    if form.is_valid():
        profile = form.save(commit=False)
        profile.clinic = clinic
        profile.patient = patient
        profile.last_verified_at = timezone.now()
        profile.last_verified_by = request.user
        profile.save()
        create_yakap_audit_event(
            clinic=clinic,
            actor=request.user,
            action=YakapAuditEvent.ACTION_PROFILE_STATUS_CHANGED,
            obj=profile,
            summary=f"Updated patient YAKAP profile status to {profile.get_status_display()}.",
        )
        messages.success(request, "YAKAP profile updated.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("dashboard:patient_detail", pk=patient.pk)


@login_required
def patient_edit(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    patient = get_object_or_404(clinic.patients, pk=pk)
    if request.method == "POST":
        form = PatientForm(clinic=clinic, data=request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Patient updated.")
            current_url = request.headers.get("HX-Current-URL", "")
            is_detail_page = f"/patients/{patient.id}/" in current_url
            if is_detail_page:
                response = render(
                    request,
                    "dashboard/partials/patient_detail_content.html",
                    _patient_detail_context(clinic, patient, membership=membership),
                )
                response["HX-Retarget"] = "#patient-detail-content"
                response["HX-Reswap"] = "innerHTML"
                response["HX-Trigger"] = json.dumps({
                    "patientSaved": True,
                    "toast-message": {"message": "Patient updated.", "type": "success"}
                })
                return response
            response = render(request, "dashboard/partials/patient_row.html", {"patient": patient})
            response["HX-Retarget"] = f"#patient-row-{patient.id}"
            response["HX-Reswap"] = "outerHTML"
            response["HX-Trigger"] = json.dumps({
                "patientSaved": True,
                "toast-message": {"message": "Patient updated.", "type": "success"}
            })
            return response
        return render(request, "dashboard/partials/patient_edit_modal_form.html", {"form": form, "patient": patient})
    else:
        form = PatientForm(clinic=clinic, instance=patient)
    return render(request, "dashboard/partials/patient_edit_modal_form.html", {"form": form, "patient": patient})


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
                "patientDeleteBlocked": True,
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


@login_required
def find_duplicates(request):
    clinic = _clinic_or_redirect(request)
    patients_qs = list(clinic.patients.all())
    duplicates = []
    seen_phones = {}
    seen_names = {}
    seen_pairs = set()
    for p in patients_qs:
        dup_pair = None
        if p.normalized_phone in seen_phones:
            dup_pair = (seen_phones[p.normalized_phone], p)
        elif p.full_name.strip().lower() in seen_names:
            dup_pair = (seen_names[p.full_name.strip().lower()], p)

        if dup_pair:
            pair_key = tuple(sorted([dup_pair[0].id, dup_pair[1].id]))
            if pair_key not in seen_pairs:
                duplicates.append(dup_pair)
                seen_pairs.add(pair_key)

        seen_phones[p.normalized_phone] = p
        seen_names[p.full_name.strip().lower()] = p
    return render(request, "dashboard/partials/duplicate_list.html", {"clinic": clinic, "duplicates": duplicates})


@login_required
def patient_merge(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    primary_id = request.POST.get("primary_id") or request.GET.get("primary_id")
    duplicate_id = request.POST.get("duplicate_id") or request.GET.get("duplicate_id")
    primary = get_object_or_404(clinic.patients, pk=primary_id) if primary_id else None
    duplicate = get_object_or_404(clinic.patients, pk=duplicate_id) if duplicate_id else None

    if request.method == "POST" and primary and duplicate:
        if primary.pk == duplicate.pk:
            return HttpResponse("Select two different patients to merge.", status=400)
        if patient_has_yakap_history(primary) or patient_has_yakap_history(duplicate):
            return HttpResponse('<p class="cf-error">Cannot merge patients with YAKAP history. Resolve YAKAP records manually before merging.</p>')
        appointment_count = duplicate.appointments.count()
        for appointment in duplicate.appointments.all():
            appointment.patient = primary
            appointment.save(update_fields=["patient", "updated_at"])
        duplicate.delete()
        messages.success(
            request,
            f"Merged {duplicate.full_name} into {primary.full_name}. {appointment_count} appointment(s) moved."
        )
        if request.headers.get("HX-Request"):
            return render(request, "dashboard/partials/merge_success.html", {"primary": primary})
        return redirect("dashboard:patients")

    return render(
        request,
        "dashboard/partials/merge_confirm.html",
        {"clinic": clinic, "primary": primary, "duplicate": duplicate},
    )


@login_required
def services(request):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    active_services = clinic.services.filter(is_archived=False).select_related("clinic", "yakap_rule")
    archived_services = clinic.services.filter(is_archived=True).select_related("clinic", "yakap_rule")
    membership = get_active_membership(request.user)
    can_manage = user_can_manage_daily_ops(membership)
    can_manage_yakap_rules = user_can_manage_settings(membership)
    return render(
        request,
        "dashboard/services.html",
        {
            "clinic": clinic,
            "active_services": active_services,
            "archived_services": archived_services,
            "form": ServiceForm(clinic),
            "yakap_rule_form": _service_yakap_rule_form(clinic) if can_manage_yakap_rules else None,
            "can_manage": can_manage,
        },
    )


@login_required
@require_POST
def create_service(request):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    form = ServiceForm(clinic, request.POST)
    form.instance.clinic = clinic
    yakap_rule_data_submitted = _service_yakap_rule_data_submitted(request.POST)
    can_manage_yakap_rules = user_can_manage_settings(membership)
    if yakap_rule_data_submitted and not can_manage_yakap_rules:
        raise PermissionDenied
    yakap_rule_form = _service_yakap_rule_form(clinic, data=request.POST) if can_manage_yakap_rules else None
    yakap_rule_valid = True if not yakap_rule_data_submitted else yakap_rule_form.is_valid()
    if form.is_valid() and yakap_rule_valid:
        service = form.save(commit=False)
        service.clinic = clinic
        try:
            with transaction.atomic():
                service.save()
                if yakap_rule_data_submitted:
                    yakap_rule_form = _save_service_yakap_rule(clinic, service, request.POST, actor=request.user)
        except ValidationError as exc:
            form.add_error(None, exc)
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "dashboard/partials/service_form.html",
                    {
                        "clinic": clinic,
                        "service": None,
                        "form": form,
                        "yakap_rule_form": yakap_rule_form,
                    },
                )
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return redirect("dashboard:services")
        if request.headers.get("HX-Request"):
            active_services = clinic.services.filter(is_archived=False).select_related("clinic", "yakap_rule")
            archived_services = clinic.services.filter(is_archived=True).select_related("clinic", "yakap_rule")
            response = render(
                request,
                "dashboard/partials/service_list.html",
                {
                    "clinic": clinic,
                    "active_services": active_services,
                    "archived_services": archived_services,
                    "form": ServiceForm(clinic),
                    "yakap_rule_form": _service_yakap_rule_form(clinic) if can_manage_yakap_rules else None,
                    "can_manage": True,
                },
            )
            response["HX-Retarget"] = "#services-list-container"
            response["HX-Reswap"] = "innerHTML"
            response["HX-Trigger"] = json.dumps({
                "serviceCreated": True,
                "toast-message": {"message": "Service created.", "type": "success"}
            })
            return response
        messages.success(request, "Service created.")
    else:
        if request.headers.get("HX-Request"):
            return render(
                request,
                "dashboard/partials/service_form.html",
                {
                    "clinic": clinic,
                    "service": None,
                    "form": form,
                    "yakap_rule_form": yakap_rule_form,
                },
            )
        error_text = form.errors.as_text() or yakap_rule_form.errors.as_text()
        messages.error(request, error_text)
    return redirect("dashboard:services")


@login_required
@require_POST
def toggle_service(request, pk):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    service = get_object_or_404(clinic.services.select_related("clinic", "yakap_rule"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    service.is_active = not service.is_active
    service.save(update_fields=["is_active", "updated_at"])
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "dashboard/partials/service_row.html",
            {"clinic": clinic, "service": service},
        )
        response["HX-Retarget"] = f"#service-card-{service.id}"
        response["HX-Reswap"] = "outerHTML"
        response["HX-Trigger"] = json.dumps({
            "toast-message": {"message": f"Service {'activated' if service.is_active else 'deactivated'}.", "type": "success"}
        })
        return response
    messages.success(request, f"Service {'activated' if service.is_active else 'deactivated'}.")
    return redirect("dashboard:services")


@login_required
def edit_service(request, pk):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    service = get_object_or_404(clinic.services.select_related("clinic", "yakap_rule"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if request.method == "POST":
        form = ServiceForm(clinic, request.POST, instance=service)
        yakap_rule_data_submitted = _service_yakap_rule_data_submitted(request.POST)
        can_manage_yakap_rules = user_can_manage_settings(membership)
        if yakap_rule_data_submitted and not can_manage_yakap_rules:
            raise PermissionDenied
        yakap_rule_form = _service_yakap_rule_form(clinic, service, request.POST) if can_manage_yakap_rules else None
        yakap_rule_valid = True if not yakap_rule_data_submitted else yakap_rule_form.is_valid()
        if form.is_valid() and yakap_rule_valid:
            with transaction.atomic():
                service = form.save()
                if yakap_rule_data_submitted:
                    yakap_rule_form = _save_service_yakap_rule(clinic, service, request.POST, actor=request.user)
            if request.headers.get("HX-Request"):
                response = render(
                    request,
                    "dashboard/partials/service_row.html",
                    {"clinic": clinic, "service": service},
                )
                response["HX-Retarget"] = f"#service-card-{service.id}"
                response["HX-Reswap"] = "outerHTML"
                response["HX-Trigger"] = json.dumps({
                    "serviceSaved": True,
                    "toast-message": {"message": "Service updated.", "type": "success"}
                })
                return response
            messages.success(request, "Service updated.")
            return redirect("dashboard:services")
        if request.headers.get("HX-Request"):
            return render(
                request,
                "dashboard/partials/service_form.html",
                {"clinic": clinic, "service": service, "form": form, "yakap_rule_form": yakap_rule_form},
            )
        error_text = form.errors.as_text() or yakap_rule_form.errors.as_text()
        messages.error(request, error_text)
        return redirect("dashboard:services")
    form = ServiceForm(clinic, instance=service)
    can_manage_yakap_rules = user_can_manage_settings(membership)
    yakap_rule_form = _service_yakap_rule_form(clinic, service) if can_manage_yakap_rules else None
    if request.headers.get("HX-Request"):
        return render(
            request,
            "dashboard/partials/service_form.html",
            {"clinic": clinic, "service": service, "form": form, "yakap_rule_form": yakap_rule_form},
        )
    return redirect("dashboard:services")


@login_required
@require_POST
def archive_service(request, pk):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    service = get_object_or_404(clinic.services, pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    service.is_archived = True
    service.save(update_fields=["is_archived", "updated_at"])
    if request.headers.get("HX-Request"):
        can_manage_yakap_rules = user_can_manage_settings(membership)
        active_services = clinic.services.filter(is_archived=False).select_related("clinic", "yakap_rule")
        archived_services = clinic.services.filter(is_archived=True).select_related("clinic", "yakap_rule")
        response = render(
            request,
            "dashboard/partials/service_list.html",
            {
                "clinic": clinic,
                "active_services": active_services,
                "archived_services": archived_services,
                "form": ServiceForm(clinic),
                "yakap_rule_form": _service_yakap_rule_form(clinic) if can_manage_yakap_rules else None,
                "can_manage": True,
            },
        )
        response["HX-Retarget"] = "#services-list-container"
        response["HX-Reswap"] = "innerHTML"
        response["HX-Trigger"] = json.dumps({
            "toast-message": {"message": "Service archived.", "type": "success"}
        })
        return response
    messages.success(request, "Service archived.")
    return redirect("dashboard:services")


@login_required
@require_POST
def restore_service(request, pk):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    service = get_object_or_404(clinic.services, pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    service.is_archived = False
    service.save(update_fields=["is_archived", "updated_at"])
    if request.headers.get("HX-Request"):
        can_manage_yakap_rules = user_can_manage_settings(membership)
        active_services = clinic.services.filter(is_archived=False).select_related("clinic", "yakap_rule")
        archived_services = clinic.services.filter(is_archived=True).select_related("clinic", "yakap_rule")
        response = render(
            request,
            "dashboard/partials/service_list.html",
            {
                "clinic": clinic,
                "active_services": active_services,
                "archived_services": archived_services,
                "form": ServiceForm(clinic),
                "yakap_rule_form": _service_yakap_rule_form(clinic) if can_manage_yakap_rules else None,
                "can_manage": True,
            },
        )
        response["HX-Retarget"] = "#services-list-container"
        response["HX-Reswap"] = "innerHTML"
        response["HX-Trigger"] = json.dumps({
            "toast-message": {"message": "Service restored.", "type": "success"}
        })
        return response
    messages.success(request, "Service restored.")
    return redirect("dashboard:services")


def _service_list_response(request, clinic, message, *, toast_type="success"):
    active_services = clinic.services.filter(is_archived=False).select_related("clinic", "yakap_rule")
    archived_services = clinic.services.filter(is_archived=True).select_related("clinic", "yakap_rule")
    membership = get_active_membership(request.user)
    can_manage_yakap_rules = user_can_manage_settings(membership)
    response = render(
        request,
        "dashboard/partials/service_list.html",
        {
            "clinic": clinic,
            "active_services": active_services,
            "archived_services": archived_services,
            "form": ServiceForm(clinic),
            "yakap_rule_form": _service_yakap_rule_form(clinic) if can_manage_yakap_rules else None,
            "can_manage": user_can_manage_daily_ops(membership),
        },
    )
    response["HX-Retarget"] = "#services-list-container"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = json.dumps({
        "toast-message": {"message": message, "type": toast_type}
    })
    return response


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


@login_required
def settings(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied

    slot_results = None
    slot_service = None
    slot_date = None
    active_tab = request.GET.get("tab") if request.GET.get("tab") in {"general", "hours", "unavailable", "preview"} else "general"
    slot_preview_services = clinic.services.filter(is_active=True, is_archived=False)

    # Discriminate slot-preview POST from general settings POST
    if request.method == "POST" and request.POST.get("date") and request.POST.get("service"):
        active_tab = "preview"
        service_id = request.POST.get("service")
        date_str = request.POST.get("date")
        if service_id and date_str:
            service_pk = None
            try:
                service_pk = _parse_service_filter(service_id)
            except ValidationError:
                pass
            slot_service = slot_preview_services.filter(pk=service_pk).first() if service_pk else None
            slot_date = parse_date(date_str)
            if slot_service and slot_date:
                slot_results = generate_slots(clinic, slot_service, slot_date)
        form = ClinicSettingsForm(instance=clinic)
    elif request.method == "POST":
        form = ClinicSettingsForm(request.POST, request.FILES, instance=clinic)
        if form.is_valid():
            form.save()
            messages.success(request, "Clinic settings saved.")
            return redirect("dashboard:settings")
    else:
        form = ClinicSettingsForm(instance=clinic)

    hours_dict = {h.weekday: h for h in clinic.business_hours.all()}
    hours_weekdays = list(range(7))
    unavailable_dates = list(clinic.unavailable_dates.all())

    return render(request, "dashboard/settings.html", {
        "clinic": clinic,
        "form": form,
        "hours_dict": hours_dict,
        "hours_weekdays": hours_weekdays,
        "unavailable_dates": unavailable_dates,
        "slot_results": slot_results,
        "slot_service": slot_service,
        "slot_date": slot_date,
        "active_tab": active_tab,
        "slot_preview_services": slot_preview_services,
    })


def _assistant_settings_context(request, clinic, *, ai_form=None, ai_provider_form=None, faq_form=None):
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    ai_provider_settings, _ = ClinicAIProviderSettings.objects.get_or_create(clinic=clinic)
    faqs = clinic.faqs.all()
    return {
        "clinic": clinic,
        "ai_form": ai_form or SharedAISettingsForm(instance=ai_settings),
        "ai_provider_form": ai_provider_form or AIProviderSettingsForm(instance=ai_provider_settings),
        "ai_provider_settings": ai_provider_settings,
        "faq_form": faq_form or ClinicFAQForm(),
        "faqs": faqs,
        "faq_total_count": faqs.count(),
        "faq_visible_count": faqs.filter(is_active=True).count(),
        "default_ai_prompt": DEFAULT_MESSENGER_AI_PROMPT,
        "default_ai_fallback_message": DEFAULT_AI_FALLBACK_MESSAGE,
    }


def _widget_embed_context(request, clinic, *, widget_form=None):
    iframe_url = _embedded_iframe_url(request, clinic)
    script_url = request.build_absolute_uri(reverse("widget:embed_js", args=[clinic.slug]))
    return {
        "clinic": clinic,
        "widget_form": widget_form or WidgetSettingsForm(instance=clinic),
        "iframe_url": iframe_url,
        "script_url": script_url,
    }


@login_required
@sensitive_post_parameters("api_key")
def assistant_settings(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)

    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    ai_provider_settings, _ = ClinicAIProviderSettings.objects.get_or_create(clinic=clinic)
    ai_form = SharedAISettingsForm(instance=ai_settings)
    ai_provider_form = AIProviderSettingsForm(instance=ai_provider_settings)
    post_form = request.POST.get("_form")

    if request.method == "POST" and post_form == "ai_settings":
        ai_form = SharedAISettingsForm(request.POST, instance=ai_settings)
        if ai_form.is_valid():
            ai_form.save()
            messages.success(request, "Shared assistant settings saved.")
            return redirect("dashboard:assistant_settings")
    elif request.method == "POST" and post_form == "ai_provider_settings":
        ai_provider_form = AIProviderSettingsForm(request.POST, instance=ai_provider_settings)
        if ai_provider_form.is_valid():
            ai_provider_form.save()
            messages.success(request, "AI provider settings saved.")
            return redirect("dashboard:assistant_settings")

    return render(
        request,
        "dashboard/assistant_settings.html",
        _assistant_settings_context(request, clinic, ai_form=ai_form, ai_provider_form=ai_provider_form),
    )


@login_required
@sensitive_post_parameters("api_key")
@require_POST
@sensitive_variables("api_key")
def ai_provider_models(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)
    provider_settings, _ = ClinicAIProviderSettings.objects.get_or_create(clinic=clinic)

    provider = (request.POST.get("provider") or provider_settings.provider or "").strip()
    if provider not in {ClinicAIProviderSettings.PROVIDER_OPENAI, ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE}:
        return JsonResponse({"success": False, "error": "Choose a supported AI provider."}, status=400)

    if provider == ClinicAIProviderSettings.PROVIDER_OPENAI:
        base_url = ClinicAIProviderSettings.OPENAI_BASE_URL
    else:
        try:
            base_url = validate_ai_provider_base_url(request.POST.get("base_url") or "")
        except ValidationError:
            return JsonResponse({"success": False, "error": "Enter a valid provider base URL."}, status=400)

    api_key = (request.POST.get("api_key") or "").strip()
    if api_key in {"", SAVED_PROVIDER_SECRET_MASK}:
        saved_base_url = ""
        if provider_settings.provider == ClinicAIProviderSettings.PROVIDER_OPENAI:
            saved_base_url = ClinicAIProviderSettings.OPENAI_BASE_URL
        elif provider_settings.provider == ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE:
            try:
                saved_base_url = validate_ai_provider_base_url(provider_settings.base_url or "")
            except ValidationError:
                saved_base_url = ""
        if provider_settings.provider == provider and saved_base_url == base_url:
            api_key = provider_settings.api_key
        else:
            api_key = ""
    if not (api_key or "").strip():
        return JsonResponse({"success": False, "error": "Enter an API key before fetching models."}, status=400)

    try:
        model_ids = fetch_available_models(base_url, api_key, clinic_id=clinic.id, provider=provider)
    except AIProviderError:
        return JsonResponse(
            {"success": False, "error": "Could not fetch models from this provider. Check the base URL and API key."},
            status=400,
        )

    return JsonResponse({"success": True, "models": [{"id": model_id, "label": model_id} for model_id in model_ids]})


@login_required
def yakap(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    can_manage_yakap_settings = user_can_manage_settings(membership)
    if request.method == "POST" and not can_manage_yakap_settings:
        raise PermissionDenied
    if request.method != "POST" and not user_can_manage_daily_ops(membership):
        raise PermissionDenied

    if can_manage_yakap_settings:
        settings_obj, _categories = ensure_default_yakap_setup(clinic)
    else:
        try:
            settings_obj = clinic.yakap_settings
        except ClinicYakapSettings.DoesNotExist:
            settings_obj = ClinicYakapSettings(clinic=clinic)
    clinic_tz = ZoneInfo(clinic.timezone)
    today = timezone.localdate(timezone.now(), clinic_tz)
    settings_form = ClinicYakapSettingsForm(instance=settings_obj)
    category_form = YakapCoverageCategoryForm(clinic=clinic)
    post_form = request.POST.get("_form")
    unverified_appointments_qs = clinic.appointments.select_related("patient", "service", "yakap_snapshot").filter(
        yakap_snapshot__requested=True,
        yakap_snapshot__coverage_status__in=[
            AppointmentYakapSnapshot.STATUS_REQUESTED,
            AppointmentYakapSnapshot.STATUS_UNVERIFIED,
            AppointmentYakapSnapshot.STATUS_NEEDS_VERIFICATION,
        ],
    ).exclude(status__in=[Appointment.STATUS_CANCELLED, Appointment.STATUS_NO_SHOW]).order_by("starts_at")
    unverified_appointments_count = unverified_appointments_qs.count()
    unverified_appointments = unverified_appointments_qs[:10]
    upcoming_yakap_appointments_qs = clinic.appointments.select_related("patient", "service", "yakap_snapshot").filter(
        starts_at__gte=timezone.now(),
        yakap_snapshot__requested=True,
        yakap_snapshot__coverage_status__in=[
            AppointmentYakapSnapshot.STATUS_REQUESTED,
            AppointmentYakapSnapshot.STATUS_UNVERIFIED,
            AppointmentYakapSnapshot.STATUS_NEEDS_VERIFICATION,
        ],
    ).exclude(status__in=[Appointment.STATUS_CANCELLED, Appointment.STATUS_NO_SHOW]).order_by("starts_at")
    upcoming_yakap_appointments_count = upcoming_yakap_appointments_qs.count()
    upcoming_yakap_appointments = upcoming_yakap_appointments_qs[:10]
    recent_ledger_entries = clinic.yakap_ledger_entries.select_related(
        "patient",
        "category",
        "service",
        "appointment",
    ).order_by("-occurred_at", "-created_at")[:10]
    services_missing_rules_qs = clinic.services.filter(
        is_active=True,
        is_archived=False,
    ).filter(
        Q(yakap_rule__isnull=True)
        | Q(yakap_rule__category__isnull=True)
        | Q(yakap_rule__category__is_active=False)
    ).order_by("name")
    services_missing_rules_count = services_missing_rules_qs.count()
    services_missing_rules = services_missing_rules_qs[:10]
    low_balance_patients = []
    over_limit_patients = []
    low_balance_patients_count = 0
    over_limit_patients_count = 0
    active_categories = list(clinic.yakap_categories.filter(is_active=True).order_by("sort_order", "name"))
    for profile in clinic.yakap_patient_profiles.select_related("patient").order_by("patient__full_name"):
        for category in active_categories:
            balance = estimated_remaining_for(profile, category, create_period=False)
            state = balance_state_for(balance, settings_obj.low_balance_threshold_amount)
            row = {"profile": profile, "patient": profile.patient, "category": category, "balance": balance, "state": state}
            if state == "low":
                low_balance_patients_count += 1
                if len(low_balance_patients) < 10:
                    low_balance_patients.append(row)
            elif state == "negative_or_exceeded":
                over_limit_patients_count += 1
                if len(over_limit_patients) < 10:
                    over_limit_patients.append(row)

    if request.method == "POST" and post_form == "settings":
        settings_form = ClinicYakapSettingsForm(request.POST, instance=settings_obj)
        if settings_form.is_valid():
            settings_obj = settings_form.save()
            create_yakap_audit_event(
                clinic=clinic,
                actor=request.user,
                action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
                obj=settings_obj,
                summary="YAKAP settings updated.",
            )
            messages.success(request, "YAKAP settings saved.")
            return redirect("dashboard:yakap")
    elif request.method == "POST" and post_form == "category":
        category_id = request.POST.get("category_id")
        category_instance = get_object_or_404(clinic.yakap_categories, pk=category_id) if category_id else None
        category_form = YakapCoverageCategoryForm(request.POST, clinic=clinic, instance=category_instance)
        if category_form.is_valid():
            category = category_form.save(commit=False)
            category.clinic = clinic
            category.save()
            action_label = "updated" if category_instance else "added"
            create_yakap_audit_event(
                clinic=clinic,
                actor=request.user,
                action=YakapAuditEvent.ACTION_SETTINGS_CHANGED,
                obj=category,
                summary=f"YAKAP coverage category {action_label}: {category.name}.",
            )
            messages.success(request, f"YAKAP coverage category {action_label}.")
            return redirect("dashboard:yakap")

    return render(
        request,
        "dashboard/yakap.html",
        {
            "clinic": clinic,
            "yakap_settings": settings_obj,
            "settings_form": settings_form,
            "category_form": category_form,
            "categories": clinic.yakap_categories.all(),
            "category_type_choices": YakapCoverageCategory.TYPE_CHOICES,
            "can_manage_yakap_settings": can_manage_yakap_settings,
            "unverified_appointments_count": unverified_appointments_count,
            "unverified_appointments": unverified_appointments,
            "upcoming_yakap_appointments_count": upcoming_yakap_appointments_count,
            "upcoming_yakap_appointments": upcoming_yakap_appointments,
            "recent_ledger_entries": recent_ledger_entries,
            "services_missing_rules_count": services_missing_rules_count,
            "services_missing_rules": services_missing_rules,
            "low_balance_patients_count": low_balance_patients_count,
            "low_balance_patients": low_balance_patients,
            "over_limit_patients_count": over_limit_patients_count,
            "over_limit_patients": over_limit_patients,
            "export_form": YakapExportForm(initial={"started_at": today.replace(month=1, day=1), "ended_at": today}),
        },
    )


@login_required
def yakap_export(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)

    form = YakapExportForm(request.GET)
    if not form.is_valid():
        messages.error(request, "Choose a valid YAKAP export date range.")
        return redirect("dashboard:yakap")

    started_at = form.cleaned_data["started_at"]
    ended_at = form.cleaned_data["ended_at"]
    clinic_tz = ZoneInfo(clinic.timezone)
    start_dt = timezone.make_aware(datetime.combine(started_at, time.min), clinic_tz)
    end_dt = timezone.make_aware(datetime.combine(ended_at + timedelta(days=1), time.min), clinic_tz)
    entries = clinic.yakap_ledger_entries.select_related(
        "patient",
        "appointment",
        "service",
        "category",
        "created_by",
    ).filter(
        occurred_at__gte=start_dt,
        occurred_at__lt=end_dt,
    ).order_by("occurred_at", "created_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="yakap-ledger-export.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "occurred_at",
        "patient",
        "appointment_reference",
        "service",
        "category",
        "entry_type",
        "amount",
        "verification_status",
        "created_by",
        "external_reference",
        "note",
    ])
    for entry in entries:
        writer.writerow([
            timezone.localtime(entry.occurred_at, clinic_tz).isoformat(),
            _safe_csv_cell(entry.patient.full_name),
            _safe_csv_cell(entry.appointment.reference_code if entry.appointment_id else ""),
            _safe_csv_cell(entry.service.name if entry.service else ""),
            _safe_csv_cell(entry.category.name),
            _safe_csv_cell(entry.entry_type),
            f"{entry.amount:.2f}",
            _safe_csv_cell(entry.verification_status),
            _safe_csv_cell(entry.created_by.get_username() if entry.created_by else ""),
            _safe_csv_cell(entry.external_reference),
            _safe_csv_cell(entry.note),
        ])

    settings_obj, _created = ClinicYakapSettings.objects.get_or_create(clinic=clinic)
    create_yakap_audit_event(
        clinic=clinic,
        actor=request.user,
        action=YakapAuditEvent.ACTION_EXPORT_CREATED,
        obj=settings_obj,
        summary=f"Exported YAKAP ledger entries from {started_at} to {ended_at}.",
    )
    return response


@login_required
def widget_embed(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)

    widget_form = WidgetSettingsForm(instance=clinic)
    if request.method == "POST":
        widget_form = WidgetSettingsForm(request.POST, instance=clinic)
        if widget_form.is_valid():
            widget_form.save()
            messages.success(request, "Widget settings saved.")
            return redirect("dashboard:widget_embed")

    return render(request, "dashboard/widget_embed.html", _widget_embed_context(request, clinic, widget_form=widget_form))


@login_required
@require_POST
def create_faq(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)
    form = ClinicFAQForm(request.POST)
    if form.is_valid():
        faq = form.save(commit=False)
        faq.clinic = clinic
        faq.save()
        messages.success(request, "FAQ added.")
        return redirect("dashboard:assistant_settings")
    messages.error(request, "Please correct the errors below.")
    return render(
        request,
        "dashboard/assistant_settings.html",
        _assistant_settings_context(request, clinic, faq_form=form),
    )


@login_required
@require_POST
def edit_faq(request, pk):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)
    faq = get_object_or_404(clinic.faqs, pk=pk)
    is_active = faq.is_active
    post_data = request.POST.copy()
    post_data["is_active"] = "true" if is_active else "false"
    form = ClinicFAQForm(post_data, instance=faq)
    if form.is_valid():
        form.save()
        if request.headers.get("HX-Request"):
            return render(request, "dashboard/partials/faq_row.html", {"faq": faq})
        messages.success(request, "FAQ updated.")
        return redirect("dashboard:assistant_settings")
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/faq_row.html", {"faq": faq, "faq_form": form, "editing": True})
    messages.error(request, "Please correct the errors below.")
    return redirect("dashboard:assistant_settings")


@login_required
@require_POST
def toggle_faq(request, pk):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)
    faq = get_object_or_404(clinic.faqs, pk=pk)
    faq.is_active = not faq.is_active
    faq.save(update_fields=["is_active", "updated_at"])
    if request.headers.get("HX-Request"):
        response = render(request, "dashboard/partials/faq_row.html", {"faq": faq})
        response["HX-Retarget"] = f"#faq-row-{faq.id}"
        response["HX-Reswap"] = "outerHTML"
        response["HX-Trigger"] = json.dumps({
            "toast-message": {"message": f"FAQ {'activated' if faq.is_active else 'deactivated'}.", "type": "success"}
        })
        return response
    messages.success(request, f"FAQ {'activated' if faq.is_active else 'deactivated'}.")
    return redirect("dashboard:assistant_settings")


@login_required
@require_POST
def delete_faq(request, pk):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)
    faq = get_object_or_404(clinic.faqs, pk=pk)
    faq.delete()
    messages.success(request, "FAQ deleted.")
    return redirect("dashboard:assistant_settings")


@login_required
def billing(request):
    clinic = _clinic_or_redirect(request)
    return render(request, "dashboard/billing.html", {"clinic": clinic})


@login_required
def search(request):
    clinic = _clinic_or_redirect(request, allow_missing=True)
    if not clinic:
        return HttpResponse("")
    query = request.GET.get("q", "").strip()
    if not query:
        return HttpResponse("")
    patients = clinic.patients.filter(Q(full_name__icontains=query) | Q(phone__icontains=query))[:5]
    services = clinic.services.filter(Q(name__icontains=query) | Q(description__icontains=query))[:5]
    appointments = clinic.appointments.select_related("patient", "service").filter(
        Q(patient__full_name__icontains=query) | Q(service__name__icontains=query)
    )[:5]
    return render(request, "dashboard/partials/search_results.html", {"patients": patients, "services": services, "appointments": appointments, "clinic": clinic})


@login_required
def profile(request):
    clinic = _clinic_or_redirect(request)
    if request.method == "POST":
        password_form = AppPasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password updated successfully.")
            return redirect("dashboard:profile")
    else:
        password_form = AppPasswordChangeForm(request.user)
    return render(request, "dashboard/profile.html", {"clinic": clinic, "password_form": password_form})


@login_required
def business_hours(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    hours = {h.weekday: h for h in clinic.business_hours.all()}
    default_open = time(9, 0)
    default_close = time(17, 0)
    default_break_start = time(12, 0)
    default_break_end = time(13, 0)
    weekdays = list(range(7))
    return render(request, "dashboard/business_hours.html", {
        "clinic": clinic,
        "hours": hours,
        "weekdays": weekdays,
        "default_open": default_open,
        "default_close": default_close,
        "default_break_start": default_break_start,
        "default_break_end": default_break_end,
    })


@login_required
@require_POST
def save_business_hours(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    try:
        rows = _validated_business_hour_rows(request)
    except ValidationError as exc:
        messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
        return redirect(f"{reverse('dashboard:settings')}?tab=hours")
    for row in rows:
        ClinicBusinessHour.objects.update_or_create(
            clinic=clinic,
            weekday=row["weekday"],
            defaults={
                "is_open": row["is_open"],
                "open_time": row["open_time"],
                "close_time": row["close_time"],
                "break_start": row["break_start"],
                "break_end": row["break_end"],
            },
        )
    messages.success(request, "Business hours saved.")
    return redirect(f"{reverse('dashboard:settings')}?tab=hours")


@login_required
def unavailable_dates(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    dates = clinic.unavailable_dates.order_by("-date")
    return render(request, "dashboard/unavailable_dates.html", {
        "clinic": clinic,
        "unavailable_dates": dates,
    })


@login_required
@require_POST
def create_unavailable_date(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    date_value = parse_date(request.POST.get("date", ""))
    reason = request.POST.get("reason", "")
    if date_value:
        UnavailableDate.objects.update_or_create(
            clinic=clinic,
            date=date_value,
            defaults={"reason": reason},
        )
        messages.success(request, "Unavailable date saved.")
    else:
        messages.error(request, "Invalid date.")
    return redirect(f"{reverse('dashboard:settings')}?tab=unavailable")


@login_required
@require_POST
def delete_unavailable_date(request, pk):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    ud = get_object_or_404(clinic.unavailable_dates, pk=pk)
    ud.delete()
    messages.success(request, "Unavailable date deleted.")
    return redirect(f"{reverse('dashboard:settings')}?tab=unavailable")


@login_required
def slot_preview(request):
    clinic = _clinic_or_redirect(request)
    services = clinic.services.filter(is_active=True, is_archived=False)
    slots = []
    selected_service = None
    selected_date = None
    if request.method == "POST":
        service_id = request.POST.get("service")
        date_str = request.POST.get("date")
        if service_id and date_str:
            service_pk = None
            try:
                service_pk = _parse_service_filter(service_id)
            except ValidationError:
                pass
            selected_service = services.filter(pk=service_pk).first() if service_pk else None
            selected_date = parse_date(date_str)
            if selected_service and selected_date:
                slots = generate_slots(clinic, selected_service, selected_date)
    return render(request, "dashboard/slot_preview.html", {
        "clinic": clinic,
        "services": services,
        "slots": slots,
        "selected_service": selected_service,
        "selected_date": selected_date,
    })


@login_required
def messenger_settings(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    from messenger.forms import MessengerConnectionForm
    from messenger.messenger_api import fetch_page_profile

    connection = getattr(clinic, "messenger_connection", None)
    post_form = request.POST.get("_form")

    if request.method == "POST" and post_form not in {None, "", "connection_settings"}:
        messages.error(request, "Shared assistant settings are managed from Assistant.")
        return redirect("dashboard:assistant_settings")

    if request.method == "POST":
        form = MessengerConnectionForm(request.POST, instance=connection)
        if form.is_valid():
            candidate = form.save(commit=False)
            candidate.clinic = clinic
            candidate.is_active = True
            page_name_warning = False

            profile = fetch_page_profile(candidate.page_access_token)
            if profile:
                meta_page_id = profile.get("id", "")
                if candidate.page_id and meta_page_id and candidate.page_id != meta_page_id:
                    form.add_error("page_id", "The Facebook Page ID does not match the Page Access Token.")
                else:
                    if meta_page_id and not candidate.page_id:
                        candidate.page_id = meta_page_id
                    candidate.page_name = profile.get("name", "")
            elif candidate.page_access_token:
                page_name_warning = True

            if not form.errors:
                connection = candidate
                connection.save()

                if page_name_warning:
                    messages.warning(request, "Messenger settings saved, but the Facebook Page name could not be refreshed.")
                else:
                    messages.success(request, "Messenger settings saved. Remember to configure the webhook in your Meta Developer Dashboard.")
                return redirect("dashboard:messenger_settings")
    else:
        form = MessengerConnectionForm(instance=connection)

    connection_is_configured = bool(
        connection
        and connection.is_active
        and connection.page_id
        and connection.page_access_token
    )
    n8n_webhook_url = request.build_absolute_uri(reverse("messenger:n8n_webhook"))
    meta_n8n_webhook_url = getattr(django_settings, "META_MESSENGER_N8N_WEBHOOK_URL", "")
    return render(request, "dashboard/messenger_settings.html", {
        "clinic": clinic,
        "connection": connection,
        "connection_is_configured": connection_is_configured,
        "form": form,
        "n8n_webhook_url": n8n_webhook_url,
        "meta_n8n_webhook_url": meta_n8n_webhook_url,
    })

@login_required
@require_POST
@never_cache
def messenger_secret_reveal(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied

    field = request.POST.get("field")
    if field not in {"app_secret", "page_access_token"}:
        return JsonResponse({"error": "Invalid secret field."}, status=400)

    connection = getattr(clinic, "messenger_connection", None)
    return JsonResponse({"value": getattr(connection, field, "") if connection else ""})


@login_required
@require_POST
def messenger_disconnect(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    connection = getattr(clinic, "messenger_connection", None)
    if connection:
        connection.is_active = False
        connection.save(update_fields=["is_active"])
        messages.success(request, "Messenger disconnected.")
    else:
        messages.info(request, "No connection found.")
    return redirect("dashboard:messenger_settings")
