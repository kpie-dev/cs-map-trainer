import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("trainer", "0003_training_selection")]

    operations = [
        migrations.CreateModel(
            name="PracticeReview",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("scenario_id", models.CharField(max_length=128)),
                (
                    "rating",
                    models.CharField(
                        choices=[
                            ("done", "Wykonane"),
                            ("easy", "Łatwe"),
                            ("hard", "Trudne"),
                            ("irrelevant", "Nietrafne"),
                        ],
                        max_length=16,
                    ),
                ),
                ("reviewed_at", models.DateTimeField()),
                ("due_at", models.DateTimeField(null=True)),
                (
                    "upload",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="practice_reviews",
                        to="trainer.upload",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("upload", "scenario_id"), name="unique_scenario_review"
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(rating="irrelevant", due_at__isnull=True)
                            | models.Q(rating__in=["done", "easy", "hard"], due_at__isnull=False)
                        ),
                        name="valid_practice_schedule",
                    ),
                ],
            },
        ),
    ]
