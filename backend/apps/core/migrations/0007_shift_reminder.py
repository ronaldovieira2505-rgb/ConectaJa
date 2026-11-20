from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_review_window_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformparameters",
            name="shift_reminder_minutes_before",
            field=models.PositiveIntegerField(
                default=1440,
                verbose_name="lembrete do turno ao prestador (min antes do início)",
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="dedup_key",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Avisos que só podem sair uma vez (ex.: lembrete de um turno). "
                    "Vazio = sem regra."
                ),
                max_length=80,
                null=True,
                unique=True,
                verbose_name="chave de idempotência",
            ),
        ),
    ]
