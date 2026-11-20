import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vacancies", "0006_assignment_contest_response"),
        ("workers", "0002_worker_suspension_indefinite"),
    ]

    operations = [
        migrations.CreateModel(
            name="FavoriteVacancy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="salva em"
                    ),
                ),
                (
                    "vacancy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorited_by",
                        to="vacancies.vacancy",
                    ),
                ),
                (
                    "worker",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favorite_vacancies",
                        to="workers.worker",
                    ),
                ),
            ],
            options={
                "verbose_name": "vaga favorita",
                "verbose_name_plural": "vagas favoritas",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("worker", "vacancy"), name="unique_favorite_vacancy"
                    )
                ],
            },
        ),
    ]
