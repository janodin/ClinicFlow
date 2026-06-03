from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.text import slugify

from clinics.models import Clinic


User = get_user_model()

_INPUT = "cf-input"


class SignUpForm(forms.Form):
    full_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Your full name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "you@clinic.com"}))
    clinic_name = forms.CharField(max_length=160, widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "Clinic name"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": _INPUT, "placeholder": "Create a password"}), min_length=8)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_clinic_name(self):
        name = self.cleaned_data["clinic_name"]
        base_slug = slugify(name)
        slug = base_slug
        counter = 2
        while Clinic.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        self.cleaned_data["clinic_slug"] = slug
        return name


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "you@clinic.com"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": _INPUT, "placeholder": "Your password"}))
