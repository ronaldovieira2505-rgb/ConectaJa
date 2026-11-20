from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0002_worker_suspension_indefinite"),
    ]

    operations = [
        migrations.AddField(
            model_name="worker",
            name="skills",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Até 7 categorias de vaga em que o prestador tem experiência (US08).",
                verbose_name="habilidades",
            ),
        ),
        migrations.AddField(
            model_name="worker",
            name="bio",
            field=models.CharField(
                blank=True,
                help_text="Sem e-mail nem telefone: o contato só é liberado depois da alocação.",
                max_length=500,
                verbose_name="resumo da experiência",
            ),
        ),
    ]
