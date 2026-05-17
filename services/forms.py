from django import forms

from .models import Service

_INPUT = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition"
_SELECT = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 bg-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition appearance-none"
_TEXTAREA = "w-full rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 transition resize-y"
_CHECKBOX = "h-5 w-5 rounded border-slate-300 text-cyan-700 focus:ring-cyan-600"
_COLOR = "h-10 w-16 rounded-lg border border-slate-200 p-1 cursor-pointer"


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            "name",
            "description",
            "duration_minutes",
            "price",
            "color",
            "is_active",
            "display_price",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Service name"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Service description", "rows": 3}),
            "duration_minutes": forms.NumberInput(attrs={"class": _INPUT, "placeholder": "30"}),
            "price": forms.NumberInput(attrs={"class": _INPUT, "placeholder": "0.00"}),
            "color": forms.TextInput(attrs={"type": "color", "class": _COLOR}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "display_price": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }

    def __init__(self, clinic, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_duration_minutes(self):
        duration = self.cleaned_data.get("duration_minutes")
        if duration is not None:
            if duration <= 0 or duration > 480:
                raise forms.ValidationError("Duration must be between 1 and 480 minutes.")
        return duration
