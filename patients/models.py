import re

from django.db import models

from clinics.models import Clinic, TimeStampedModel


def normalize_phone(value):
    return re.sub(r"\D+", "", value or "")


class Patient(TimeStampedModel):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="patients")
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40)
    normalized_phone = models.CharField(max_length=40, db_index=True)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["clinic", "normalized_phone"])]

    def save(self, *args, **kwargs):
        self.normalized_phone = normalize_phone(self.phone)
        super().save(*args, **kwargs)

    @property
    def formatted_phone(self):
        from .utils import format_phone_display
        return format_phone_display(self.phone)

    @classmethod
    def find_or_create_for_booking(cls, clinic, full_name, phone, email="", notes=""):
        normalized = normalize_phone(phone)
        patient = cls.objects.filter(clinic=clinic, normalized_phone=normalized).order_by("created_at").first()
        if patient:
            changed = False
            if email and not patient.email:
                patient.email = email
                changed = True
            if full_name and patient.full_name != full_name and len(full_name) > len(patient.full_name):
                patient.full_name = full_name
                changed = True
            if notes and not patient.notes:
                patient.notes = notes
                changed = True
            if changed:
                patient.save()
            return patient, False
        return cls.objects.create(clinic=clinic, full_name=full_name, phone=phone, email=email, notes=notes), True

    def __str__(self):
        return self.full_name

# Create your models here.
