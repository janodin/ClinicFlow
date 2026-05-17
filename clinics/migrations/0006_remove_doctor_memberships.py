from django.db import migrations


def remove_doctor_memberships(apps, schema_editor):
    ClinicMembership = apps.get_model("clinics", "ClinicMembership")
    ClinicMembership.objects.filter(role="doctor").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("clinics", "0005_alter_clinicmembership_role"),
    ]

    operations = [
        migrations.RunPython(remove_doctor_memberships, migrations.RunPython.noop),
    ]
