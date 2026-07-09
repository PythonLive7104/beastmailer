import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('workspaces', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Proxy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(help_text="Friendly name, e.g. 'Residential US-1'", max_length=120)),
                ('kind', models.CharField(choices=[('socks5', 'SOCKS5'), ('socks4', 'SOCKS4'), ('http', 'HTTP CONNECT')], default='socks5', max_length=10)),
                ('host', models.CharField(max_length=200)),
                ('port', models.PositiveIntegerField()),
                ('username', models.CharField(blank=True, default='', max_length=200)),
                ('password_encrypted', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True, default='')),
                ('failure_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proxies', to='workspaces.workspace')),
            ],
            options={
                'verbose_name_plural': 'proxies',
                'ordering': ['label'],
            },
        ),
    ]
