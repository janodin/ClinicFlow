from django import forms

from .models import Service

_INPUT = "cf-input"
_SELECT = "cf-select"
_TEXTAREA = "cf-textarea"
_CHECKBOX = "cf-checkbox"
_COLOR = "h-10 w-20 rounded-xl border border-[var(--cf-line)] p-1 cursor-pointer"


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            "name",
            "description",
            "duration_minutes",
            "color",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Service name"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Service description", "rows": 3}),
            "duration_minutes": forms.NumberInput(attrs={"class": _INPUT, "placeholder": "30"}),
            "color": forms.TextInput(attrs={"type": "color", "class": _COLOR}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }

    def __init__(self, clinic, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_duration_minutes(self):
        duration = self.cleaned_data.get("duration_minutes")
        if duration is not None:
            if duration <= 0 or duration > 480:
                raise forms.ValidationError("Duration must be between 1 and 480 minutes.")
        return duration
