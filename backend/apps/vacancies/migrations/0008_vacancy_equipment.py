from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vacancies", "0007_favoritevacancy"),
    ]

    operations = [
        migrations.AddField(
            model_name="vacancy",
            name="equipment",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Itens da lista fixa com quem providencia: [{"item", "provider"}] (US22).',
                verbose_name="EPIs, uniforme e ferramentas",
            ),
        ),
        migrations.AddField(
            model_name="vacancy",
            name="equipment_notes",
            field=models.CharField(
                blank=True, max_length=300, verbose_name="observações sobre o que levar"
            ),
        ),
    ]
