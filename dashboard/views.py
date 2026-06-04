import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.conf import settings as django_settings

from appointments.forms import AppointmentNoteForm, AppointmentStatusForm, StaffAppointmentForm
from appointments.models import Appointment
from clinics.forms import ClinicFAQForm, ClinicSettingsForm, SharedAISettingsForm, WidgetSettingsForm
from clinics.models import Clinic, ClinicAISettings, ClinicMembership
from clinics.tenant import current_clinic, get_active_membership, user_can_manage_daily_ops, user_can_manage_settings
from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from scheduling.models import ClinicBusinessHour, UnavailableDate
from scheduling.utils import _date_is_unavailable, _inside_break, generate_slots, get_working_window, validate_slot
from patients.forms import PatientForm
from patients.models import Patient
from services.forms import ServiceForm


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


def _require_settings_permission(user):
    membership = get_active_membership(user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied


def _calendar_modal_trigger(message, *, close=False, refetch=True):
    trigger = {"toast-message": {"message": message, "type": "success"}}
    if refetch:
        trigger["calendar-refetch"] = True
    if close:
        trigger["close-calendar-modal"] = True
    return json.dumps(trigger)


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
    needs_attention = appointments.filter(status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_NO_SHOW])[:6]
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
        "needs_attention": needs_attention,
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

    for appointment in qs:
        colors = color_map.get(appointment.status, {})
        local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
        starts_at_label = local_start.strftime("%I:%M %p").lstrip("0").lower()
        is_reschedulable = appointment.status not in {
            Appointment.STATUS_COMPLETED,
            Appointment.STATUS_CANCELLED,
        }
        events.append(
            {
                "id": appointment.id,
                "title": f"{starts_at_label} {appointment.patient.full_name}",
                "start": appointment.starts_at.isoformat(),
                "end": appointment.ends_at.isoformat(),
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
    qs = clinic.appointments.select_related("patient", "service").all()
    search_query = request.GET.get("q", "").strip()
    if search_query:
        qs = qs.filter(
            Q(patient__full_name__icontains=search_query)
            | Q(patient__phone__icontains=search_query)
            | Q(service__name__icontains=search_query)
            | Q(reference_code__icontains=search_query)
        )
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        qs = qs.filter(starts_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(starts_at__date__lte=date_to)
    service_filter = request.GET.get("service")
    if service_filter:
        qs = qs.filter(service_id=service_filter)
    source_filter = request.GET.get("source")
    if source_filter:
        qs = qs.filter(source=source_filter)
    payment_filter = request.GET.get("payment_state")
    if payment_filter:
        qs = qs.filter(payment_state=payment_filter)
    qs = qs.order_by("-starts_at")
    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    form = StaffAppointmentForm(clinic)
    context = {
        "clinic": clinic,
        "appointments": page_obj,
        "page_obj": page_obj,
        "form": form,
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
    init_mode = request.GET.get("mode", "detail")
    if init_mode not in {"detail", "cancel", "reschedule"}:
        init_mode = "detail"
    context = {
        "clinic": clinic,
        "appointment": appointment,
        "status_form": AppointmentStatusForm(instance=appointment),
        "note_form": AppointmentNoteForm(),
        "init_mode": init_mode,
        "source": request.GET.get("source", ""),
    }
    return render(request, "dashboard/partials/appointment_detail.html", context)


@login_required
def appointment_edit(request, pk):
    clinic = _clinic_or_redirect(request)
    appointment = get_object_or_404(clinic.appointments.select_related("patient", "service"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if request.method == "POST":
        with transaction.atomic():
            clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
            form = StaffAppointmentForm(clinic, request.POST, instance=appointment)
            if form.is_valid():
                patient, _ = Patient.find_or_create_for_booking(
                    clinic=clinic,
                    full_name=form.cleaned_data["patient_name"],
                    phone=form.cleaned_data["patient_phone"],
                    email=form.cleaned_data["patient_email"],
                )
                appointment = form.save(commit=False)
                appointment.patient = patient
                appointment.save()
            else:
                if request.headers.get("HX-Request"):
                    return render(request, "dashboard/partials/appointment_form.html", {
                        "form": form,
                        "appointment": appointment,
                        "patient_form": PatientForm(clinic=clinic),
                        "source": request.POST.get("modal_source", ""),
                    })
                messages.error(request, form.errors.as_text())
                return redirect("dashboard:appointments")
        if form.is_valid():
            if request.headers.get("HX-Request"):
                if request.POST.get("modal_source") == "calendar":
                    response = render(request, "dashboard/partials/appointment_detail.html", {
                        "appointment": appointment,
                        "status_form": AppointmentStatusForm(instance=appointment),
                        "note_form": AppointmentNoteForm(),
                        "source": "calendar",
                    })
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
    appointment = get_object_or_404(clinic.appointments, pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if not appointment.can_transition_to(Appointment.STATUS_CANCELLED):
        return _redirect_with_appointment_error(request, "Cannot cancel this appointment from its current status.")
    reason = request.POST.get("cancellation_reason", "")
    appointment.status = Appointment.STATUS_CANCELLED
    appointment.cancellation_reason = reason
    appointment.save()
    if request.headers.get("HX-Request"):
        if request.POST.get("modal_source") == "calendar":
            response = HttpResponse("")
            response["HX-Trigger"] = _calendar_modal_trigger("Appointment cancelled.", close=True)
            return response
        response = render(request, "dashboard/partials/appointment_row.html", {"appointment": appointment})
        response["HX-Retarget"] = f"#appointment-row-{appointment.pk}"
        response["HX-Reswap"] = "outerHTML"
        response["HX-Trigger"] = json.dumps({
            "appointmentSaved": True,
            "toast-message": {"message": "Appointment cancelled.", "type": "success"}
        })
        return response
    messages.success(request, "Appointment cancelled.")
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
        if request.POST.get("modal_source") == "calendar":
            response = HttpResponse("")
            response["HX-Trigger"] = _calendar_modal_trigger("Appointment rescheduled.", close=True)
            return response
        response = render(request, "dashboard/partials/appointment_row.html", {"appointment": appointment})
        response["HX-Retarget"] = f"#appointment-row-{appointment.pk}"
        response["HX-Reswap"] = "outerHTML"
        response["HX-Trigger"] = json.dumps({
            "appointmentSaved": True,
            "toast-message": {"message": "Appointment rescheduled.", "type": "success"}
        })
        return response
    messages.success(request, "Appointment rescheduled.")
    return redirect("dashboard:appointments")


@login_required
def export_csv(request):
    clinic = _clinic_or_redirect(request)
    qs = clinic.appointments.select_related("patient", "service").all()
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        qs = qs.filter(starts_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(starts_at__date__lte=date_to)
    service_filter = request.GET.get("service")
    if service_filter:
        qs = qs.filter(service_id=service_filter)
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
    for appt in qs:
        writer.writerow([
            appt.id,
            appt.patient.full_name,
            appt.patient.phone,
            appt.service.name,
            appt.starts_at.strftime("%Y-%m-%d"),
            appt.starts_at.strftime("%H:%M"),
            appt.get_status_display(),
            appt.get_source_display(),
            appt.get_payment_state_display(),
            appt.created_at.strftime("%Y-%m-%d %H:%M"),
        ])
    return response


@login_required
@require_POST
def update_appointment(request, pk):
    clinic = _clinic_or_redirect(request)
    appointment = get_object_or_404(clinic.appointments, pk=pk)
    form = AppointmentStatusForm(request.POST, instance=appointment)
    updated = form.is_valid()
    if updated:
        form.save()
        messages.success(request, "Appointment updated.")
    else:
        appointment.refresh_from_db()
    if request.headers.get("HX-Request"):
        response = render(request, "dashboard/partials/appointment_detail.html", {
            "appointment": appointment,
            "status_form": AppointmentStatusForm(instance=appointment) if updated else form,
            "note_form": AppointmentNoteForm(),
            "source": request.POST.get("modal_source", ""),
        })
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
    appointment = get_object_or_404(clinic.appointments, pk=pk)
    form = AppointmentNoteForm(request.POST)
    added = form.is_valid()
    if added:
        note = form.save(commit=False)
        note.appointment = appointment
        note.author = request.user
        note.save()
        messages.success(request, "Note added.")
    if request.headers.get("HX-Request"):
        response = render(request, "dashboard/partials/appointment_detail.html", {
            "appointment": appointment,
            "status_form": AppointmentStatusForm(instance=appointment),
            "note_form": AppointmentNoteForm() if added else form,
            "source": request.POST.get("modal_source", ""),
        })
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
def patients(request):
    clinic = _clinic_or_redirect(request)
    query = request.GET.get("q", "").strip()
    qs = clinic.patients.order_by("-created_at", "-id")
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {
        "clinic": clinic,
        "patients": page_obj,
        "page_obj": page_obj,
        "patient_form": PatientForm(clinic=clinic),
        "query": query,
    }
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/patient_list.html", context)
    return render(request, "dashboard/patients.html", context)


@login_required
@require_POST
def create_patient(request):
    clinic = _clinic_or_redirect(request)
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
    patient = get_object_or_404(
        clinic.patients.prefetch_related(
            "appointments__service",
        ),
        pk=pk,
    )
    appointments = patient.appointments.all()
    total = appointments.count()
    upcoming = appointments.filter(status__in=["pending", "confirmed"], starts_at__gte=timezone.now()).count()
    completed = appointments.filter(status="completed").count()
    cancelled = appointments.filter(status__in=["cancelled", "no_show"]).count()
    last_appointment = appointments.order_by("starts_at").last()
    context = {
        "clinic": clinic,
        "patient": patient,
        "kpi_total": total,
        "kpi_upcoming": upcoming,
        "kpi_completed": completed,
        "kpi_cancelled": cancelled,
        "last_appointment": last_appointment,
    }
    return render(request, "dashboard/partials/patient_detail.html", context)


@login_required
def patient_edit(request, pk):
    clinic = _clinic_or_redirect(request)
    patient = get_object_or_404(clinic.patients, pk=pk)
    if request.method == "POST":
        form = PatientForm(clinic=clinic, data=request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, "Patient updated.")
            current_url = request.headers.get("HX-Current-URL", "")
            is_detail_page = f"/patients/{patient.id}/" in current_url
            if is_detail_page:
                response = render(request, "dashboard/partials/patient_detail_content.html", {
                    "clinic": clinic,
                    "patient": patient,
                    "kpi_total": patient.appointments.count(),
                    "kpi_upcoming": patient.appointments.filter(status__in=["pending", "confirmed"], starts_at__gte=timezone.now()).count(),
                    "kpi_completed": patient.appointments.filter(status="completed").count(),
                    "kpi_cancelled": patient.appointments.filter(status__in=["cancelled", "no_show"]).count(),
                    "last_appointment": patient.appointments.order_by("starts_at").last(),
                })
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
    primary_id = request.POST.get("primary_id") or request.GET.get("primary_id")
    duplicate_id = request.POST.get("duplicate_id") or request.GET.get("duplicate_id")
    primary = get_object_or_404(clinic.patients, pk=primary_id) if primary_id else None
    duplicate = get_object_or_404(clinic.patients, pk=duplicate_id) if duplicate_id else None

    if request.method == "POST" and primary and duplicate:
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
    active_services = clinic.services.filter(is_archived=False).select_related("clinic")
    archived_services = clinic.services.filter(is_archived=True).select_related("clinic")
    membership = get_active_membership(request.user)
    can_manage = user_can_manage_daily_ops(membership)
    return render(
        request,
        "dashboard/services.html",
        {
            "clinic": clinic,
            "active_services": active_services,
            "archived_services": archived_services,
            "form": ServiceForm(clinic),
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
    if form.is_valid():
        service = form.save(commit=False)
        service.clinic = clinic
        try:
            service.save()
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
                    },
                )
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return redirect("dashboard:services")
        if request.headers.get("HX-Request"):
            active_services = clinic.services.filter(is_archived=False).select_related("clinic")
            archived_services = clinic.services.filter(is_archived=True).select_related("clinic")
            response = render(
                request,
                "dashboard/partials/service_list.html",
                {
                    "clinic": clinic,
                    "active_services": active_services,
                    "archived_services": archived_services,
                    "form": ServiceForm(clinic),
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
                },
            )
        messages.error(request, form.errors.as_text())
    return redirect("dashboard:services")


@login_required
@require_POST
def toggle_service(request, pk):
    clinic = _clinic_or_redirect(request)
    if not clinic:
        return redirect("accounts:signup")
    service = get_object_or_404(clinic.services.select_related("clinic"), pk=pk)
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
    service = get_object_or_404(clinic.services.select_related("clinic"), pk=pk)
    membership = get_active_membership(request.user)
    if not user_can_manage_daily_ops(membership):
        raise PermissionDenied
    if request.method == "POST":
        form = ServiceForm(clinic, request.POST, instance=service)
        if form.is_valid():
            form.save()
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
                {"clinic": clinic, "service": service, "form": form},
            )
        messages.error(request, form.errors.as_text())
        return redirect("dashboard:services")
    form = ServiceForm(clinic, instance=service)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "dashboard/partials/service_form.html",
            {"clinic": clinic, "service": service, "form": form},
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
        active_services = clinic.services.filter(is_archived=False).select_related("clinic")
        archived_services = clinic.services.filter(is_archived=True).select_related("clinic")
        response = render(
            request,
            "dashboard/partials/service_list.html",
            {
                "clinic": clinic,
                "active_services": active_services,
                "archived_services": archived_services,
                "form": ServiceForm(clinic),
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
        active_services = clinic.services.filter(is_archived=False).select_related("clinic")
        archived_services = clinic.services.filter(is_archived=True).select_related("clinic")
        response = render(
            request,
            "dashboard/partials/service_list.html",
            {
                "clinic": clinic,
                "active_services": active_services,
                "archived_services": archived_services,
                "form": ServiceForm(clinic),
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

    # Discriminate slot-preview POST from general settings POST
    if request.method == "POST" and request.POST.get("date") and request.POST.get("service"):
        service_id = request.POST.get("service")
        date_str = request.POST.get("date")
        if service_id and date_str:
            from datetime import date as date_class
            slot_service = get_object_or_404(clinic.services.filter(is_active=True, is_archived=False), pk=service_id)
            try:
                slot_date = date_class.fromisoformat(date_str)
                if slot_service:
                    slot_results = generate_slots(clinic, slot_service, slot_date)
            except ValueError:
                pass
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
    })


def _assistant_settings_context(request, clinic, *, widget_form=None, ai_form=None, faq_form=None):
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    faqs = clinic.faqs.all()
    iframe_url = _embedded_iframe_url(request, clinic)
    script_url = request.build_absolute_uri(reverse("widget:embed_js", args=[clinic.slug]))
    return {
        "clinic": clinic,
        "widget_form": widget_form or WidgetSettingsForm(instance=clinic),
        "ai_form": ai_form or SharedAISettingsForm(instance=ai_settings),
        "faq_form": faq_form or ClinicFAQForm(),
        "faqs": faqs,
        "faq_total_count": faqs.count(),
        "faq_visible_count": faqs.filter(is_active=True).count(),
        "iframe_url": iframe_url,
        "script_url": script_url,
        "default_ai_prompt": DEFAULT_MESSENGER_AI_PROMPT,
        "default_ai_fallback_message": DEFAULT_AI_FALLBACK_MESSAGE,
    }


@login_required
def assistant_settings(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)

    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    widget_form = WidgetSettingsForm(instance=clinic)
    ai_form = SharedAISettingsForm(instance=ai_settings)
    post_form = request.POST.get("_form")

    if request.method == "POST" and post_form == "ai_settings":
        ai_form = SharedAISettingsForm(request.POST, instance=ai_settings)
        if ai_form.is_valid():
            ai_form.save()
            messages.success(request, "Shared assistant settings saved.")
            return redirect("dashboard:assistant_settings")
    elif request.method == "POST" and post_form == "widget_settings":
        widget_form = WidgetSettingsForm(request.POST, instance=clinic)
        if widget_form.is_valid():
            widget_form.save()
            messages.success(request, "Widget settings saved.")
            return redirect("dashboard:assistant_settings")

    return render(
        request,
        "dashboard/assistant_settings.html",
        _assistant_settings_context(request, clinic, widget_form=widget_form, ai_form=ai_form),
    )


@login_required
def widget_embed(request):
    clinic = _clinic_or_redirect(request)
    iframe_url = _embedded_iframe_url(request, clinic)
    script_url = request.build_absolute_uri(reverse("widget:embed_js", args=[clinic.slug]))
    return render(request, "dashboard/widget_embed.html", {"clinic": clinic, "iframe_url": iframe_url, "script_url": script_url})


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
    return render(request, "dashboard/profile.html", {"clinic": clinic})


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
            selected_service = get_object_or_404(services, pk=service_id)
            selected_date = parse_date(date_str)
            if selected_date:
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

    n8n_webhook_url = request.build_absolute_uri(reverse("messenger:n8n_webhook"))
    return render(request, "dashboard/messenger_settings.html", {
        "clinic": clinic,
        "connection": connection,
        "form": form,
        "n8n_webhook_url": n8n_webhook_url,
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
