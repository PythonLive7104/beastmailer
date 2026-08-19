from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workspaces", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_completed",
            field=models.BooleanField(default=False),
        ),
    ]
