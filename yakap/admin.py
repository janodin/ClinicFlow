from django.contrib import admin

from clinics.admin_mixins import SuperuserOnlyAdminMixin

from .models import (
    AppointmentYakapSnapshot,
    ClinicYakapSettings,
    PatientYakapProfile,
    ServiceYakapRule,
    YakapCoverageCategory,
    YakapLedgerEntry,
)


class YakapAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    pass


admin.site.register(ClinicYakapSettings, YakapAdmin)
admin.site.register(YakapCoverageCategory, YakapAdmin)
admin.site.register(ServiceYakapRule, YakapAdmin)
admin.site.register(PatientYakapProfile, YakapAdmin)
admin.site.register(AppointmentYakapSnapshot, YakapAdmin)
admin.site.register(YakapLedgerEntry, YakapAdmin)
