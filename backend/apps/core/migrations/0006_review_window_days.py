from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_document_max_size_mb"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformparameters",
            name="review_window_days",
            field=models.PositiveIntegerField(
                default=7,
                verbose_name="prazo para avaliar após a aprovação das horas (dias)",
            ),
        ),
    ]
