from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Clinic owner/staff login user. Patients remain guest records in V1."""

    def display_name(self):
        return self.get_full_name() or self.email or self.username

# Create your models here.
