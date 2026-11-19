from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vacancies", "0005_vacancy_auto_call_waitlist"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="contest_response",
            field=models.TextField(
                blank=True,
                help_text="Resposta única e definitiva (US58).",
                verbose_name="resposta do prestador à contestação",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="contest_response_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="resposta à contestação enviada em",
            ),
        ),
    ]
