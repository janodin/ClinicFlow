from django import forms

from .models import Patient
from .utils import normalize_phone


_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ["full_name", "phone", "email", "date_of_birth", "notes"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Patient full name"}),
            "phone": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Phone number"}),
            "email": forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": _INPUT}),
            "notes": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Additional notes...", "rows": 3}),
        }

    def __init__(self, clinic=None, *args, **kwargs):
        self.clinic = clinic
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "")
        normalized = normalize_phone(phone)
        if not normalized:
            raise forms.ValidationError("Phone number is required.")
        qs = Patient.objects.filter(clinic=self.clinic, normalized_phone=normalized)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A patient with this phone number already exists in this clinic.")
        return phone
