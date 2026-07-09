from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mailboxes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='mailbox',
            name='use_proxy',
            field=models.BooleanField(default=False),
        ),
    ]
