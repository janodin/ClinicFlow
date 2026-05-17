from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from clinics.models import Clinic, TimeStampedModel


class Service(TimeStampedModel):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))]
    )
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    display_price = models.BooleanField(default=True)
    color = models.CharField(max_length=7, default="#0891b2")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["clinic", "name"], name="unique_service_name_per_clinic"),
        ]

    def clean(self):
        super().clean()
        if self.duration_minutes is not None:
            if self.duration_minutes <= 0 or self.duration_minutes > 480:
                raise ValidationError({"duration_minutes": "Duration must be between 1 and 480 minutes."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def effective_duration(self):
        return self.duration_minutes or self.clinic.default_appointment_duration or 30

    def __str__(self):
        return self.name
