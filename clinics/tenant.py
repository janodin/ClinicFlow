from django.shortcuts import redirect

from .models import Clinic, ClinicMembership


def get_active_membership(user):
    if not user.is_authenticated:
        return None
    return (
        ClinicMembership.objects.select_related("clinic", "clinic__group")
        .filter(user=user, clinic__is_active=True)
        .order_by("created_at")
        .first()
    )


def current_clinic(request):
    membership = get_active_membership(request.user)
    return membership.clinic if membership else None


class ClinicRequiredMixin:
    clinic = None
    membership = None

    def dispatch(self, request, *args, **kwargs):
        self.membership = get_active_membership(request.user)
        if not self.membership:
            return redirect("accounts:signup")
        self.clinic = self.membership.clinic
        return super().dispatch(request, *args, **kwargs)


def user_can_manage_settings(membership):
    return membership and membership.role == ClinicMembership.ROLE_OWNER


def user_can_manage_daily_ops(membership):
    return membership and membership.role in {ClinicMembership.ROLE_OWNER, ClinicMembership.ROLE_STAFF}
