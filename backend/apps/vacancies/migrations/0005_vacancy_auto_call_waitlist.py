from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vacancies', '0004_vacancy_photo'),
    ]

    operations = [
        migrations.AddField(
            model_name='vacancy',
            name='auto_call_waitlist',
            field=models.BooleanField(default=True, verbose_name='chamar automaticamente da lista de espera'),
        ),
    ]
