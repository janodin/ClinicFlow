from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Clinic owner/staff login user. Patients remain guest records in V1."""

    terms_accepted_at = models.DateTimeField(blank=True, null=True)

    def display_name(self):
        return self.get_full_name() or self.email or self.username

# Create your models here.
