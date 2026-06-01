from django.db import models

from clinics.models import Clinic, TimeStampedModel


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class ClinicBusinessHour(TimeStampedModel):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="business_hours")
    weekday = models.IntegerField(choices=Weekday.choices)
    is_open = models.BooleanField(default=True)
    open_time = models.TimeField()
    close_time = models.TimeField()
    break_start = models.TimeField(blank=True, null=True)
    break_end = models.TimeField(blank=True, null=True)

    class Meta:
        unique_together = [("clinic", "weekday")]
        ordering = ["weekday"]


class UnavailableDate(TimeStampedModel):
    clinic = models.ForeignKey(Clinic, on_delete=models.CASCADE, related_name="unavailable_dates")
    date = models.DateField()
    reason = models.CharField(max_length=160, blank=True)

    class Meta:
        unique_together = [("clinic", "date")]
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} - {self.reason or 'Unavailable'}"

# Create your models here.
