from zoneinfo import available_timezones

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.utils.dateparse import parse_time
from django.utils.text import slugify

from clinics.models import Clinic
from scheduling.models import Weekday


User = get_user_model()

_INPUT = "cf-input"
_PASSWORD_INPUT = "cf-input cf-password-input"
_TIMEZONE_CHOICES = sorted((tz, tz) for tz in available_timezones())


class SignUpForm(forms.Form):
    full_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Your full name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "you@clinic.com"}))
    clinic_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Clinic name"}))
    timezone = forms.ChoiceField(choices=_TIMEZONE_CHOICES, initial="Asia/Manila", widget=forms.Select(attrs={"class": "cf-select"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": _PASSWORD_INPUT, "placeholder": "Create a password"}), min_length=8)
    password_confirm = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"class": _PASSWORD_INPUT, "placeholder": "Confirm your password"}))
    terms_accepted = forms.BooleanField(
        label="I agree to KliniAssist's terms and privacy policy.",
        error_messages={"required": "You must accept the terms and privacy policy."},
        widget=forms.CheckboxInput(attrs={"class": "cf-checkbox"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        email = cleaned_data.get("email")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        if password:
            user = User(username=email or "", email=email or "")
            try:
                validate_password(password, user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_clinic_name(self):
        name = self.cleaned_data["clinic_name"]
        base_slug = slugify(name) or "clinic"
        slug = base_slug
        counter = 2
        while Clinic.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        self.cleaned_data["clinic_slug"] = slug
        return name


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "you@clinic.com"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": _PASSWORD_INPUT, "placeholder": "Your password"}))


class AppPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Email address"
        self.fields["email"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "you@clinic.com",
                "autocomplete": "email",
            }
        )


class AppSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "New password"
        self.fields["new_password1"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Create a new password",
                "autocomplete": "new-password",
            }
        )
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["new_password2"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Confirm your new password",
                "autocomplete": "new-password",
            }
        )


class AppPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Current password"
        self.fields["old_password"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Enter your current password",
                "autocomplete": "current-password",
            }
        )
        self.fields["new_password1"].label = "New password"
        self.fields["new_password1"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Create a new password",
                "autocomplete": "new-password",
            }
        )
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["new_password2"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Confirm your new password",
                "autocomplete": "new-password",
            }
        )


class FirstRunOnboardingForm(forms.Form):
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": _INPUT, "rows": 3}))
    phone = forms.CharField(required=False, max_length=40, widget=forms.TextInput(attrs={"class": _INPUT}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INPUT}))
    timezone = forms.ChoiceField(choices=_TIMEZONE_CHOICES, widget=forms.Select(attrs={"class": "cf-select"}))
    default_appointment_duration = forms.IntegerField(min_value=1, max_value=480, widget=forms.NumberInput(attrs={"class": _INPUT}))
    booking_approval_mode = forms.ChoiceField(choices=Clinic.APPROVAL_CHOICES, widget=forms.Select(attrs={"class": "cf-select"}))
    service_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT}))
    service_duration_minutes = forms.IntegerField(min_value=1, max_value=480, widget=forms.NumberInput(attrs={"class": _INPUT}))

    def __init__(self, *args, clinic=None, service=None, **kwargs):
        self.clinic = clinic
        self.service = service
        self.business_hour_rows = []
        super().__init__(*args, **kwargs)

        for weekday, label in Weekday.choices:
            self.fields[f"is_open_{weekday}"] = forms.BooleanField(required=False, label=label, widget=forms.CheckboxInput(attrs={"class": "cf-checkbox", "aria-label": f"{label} open"}))
            self.fields[f"open_time_{weekday}"] = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"class": _INPUT, "type": "time", "aria-label": f"{label} open time"}, format="%H:%M"), input_formats=["%H:%M"])
            self.fields[f"close_time_{weekday}"] = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"class": _INPUT, "type": "time", "aria-label": f"{label} close time"}, format="%H:%M"), input_formats=["%H:%M"])
            self.fields[f"break_start_{weekday}"] = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"class": _INPUT, "type": "time", "aria-label": f"{label} break start"}, format="%H:%M"), input_formats=["%H:%M"])
            self.fields[f"break_end_{weekday}"] = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"class": _INPUT, "type": "time", "aria-label": f"{label} break end"}, format="%H:%M"), input_formats=["%H:%M"])

        if clinic and not self.is_bound:
            self._set_initial_values(clinic, service)

    def _set_initial_values(self, clinic, service):
        self.initial.update(
            {
                "address": clinic.address,
                "phone": clinic.phone,
                "email": clinic.email,
                "timezone": clinic.timezone,
                "default_appointment_duration": clinic.default_appointment_duration,
                "booking_approval_mode": clinic.booking_approval_mode,
                "service_name": service.name if service else "General Consultation",
                "service_duration_minutes": service.duration_minutes if service and service.duration_minutes else clinic.default_appointment_duration,
            }
        )
        hours = {hour.weekday: hour for hour in clinic.business_hours.all()}
        for weekday in range(7):
            hour = hours.get(weekday)
            self.initial[f"is_open_{weekday}"] = hour.is_open if hour else weekday < 5
            self.initial[f"open_time_{weekday}"] = hour.open_time if hour else parse_time("09:00")
            self.initial[f"close_time_{weekday}"] = hour.close_time if hour else parse_time("17:00")
            self.initial[f"break_start_{weekday}"] = hour.break_start if hour else (parse_time("12:00") if weekday < 5 else None)
            self.initial[f"break_end_{weekday}"] = hour.break_end if hour else (parse_time("13:00") if weekday < 5 else None)

    def clean_service_name(self):
        name = self.cleaned_data["service_name"]
        if self.clinic:
            services = self.clinic.services.filter(name=name)
            if self.service and self.service.pk:
                services = services.exclude(pk=self.service.pk)
            if services.exists():
                raise forms.ValidationError("A service with this name already exists.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        rows = []
        for weekday in range(7):
            is_open = cleaned_data.get(f"is_open_{weekday}", False)
            open_time = cleaned_data.get(f"open_time_{weekday}")
            close_time = cleaned_data.get(f"close_time_{weekday}")
            break_start = cleaned_data.get(f"break_start_{weekday}")
            break_end = cleaned_data.get(f"break_end_{weekday}")

            if is_open:
                if not open_time:
                    self.add_error(f"open_time_{weekday}", "Open time is required for open days.")
                if not close_time:
                    self.add_error(f"close_time_{weekday}", "Close time is required for open days.")
                if open_time and close_time and open_time >= close_time:
                    self.add_error(f"close_time_{weekday}", "Close time must be after open time.")
            else:
                open_time = open_time or parse_time("09:00")
                close_time = close_time or parse_time("17:00")

            if bool(break_start) != bool(break_end):
                self.add_error(f"break_start_{weekday}", "Break start and end times must be provided together.")
            if break_start and break_end:
                if break_start >= break_end:
                    self.add_error(f"break_end_{weekday}", "Break end must be after break start.")
                if is_open and open_time and close_time and (break_start < open_time or break_end > close_time):
                    self.add_error(f"break_start_{weekday}", "Break times must be inside working hours.")

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
        self.business_hour_rows = rows
        return cleaned_data
