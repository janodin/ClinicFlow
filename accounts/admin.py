from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import User


@admin.register(User)
class AppUserAdmin(SuperuserOnlyAdminMixin, UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_staff")

# Register your models here.
