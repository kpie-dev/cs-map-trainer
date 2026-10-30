from django.db import migrations


def forwards(apps, schema_editor):
    Upload = apps.get_model("trainer", "Upload")
    Result = apps.get_model("trainer", "PlayerAnalysis")
    Review = apps.get_model("trainer", "PracticeReview")
    alias = schema_editor.connection.alias
    for upload in Upload.objects.using(alias).all().iterator(chunk_size=100):
        result = Result.objects.using(alias).create(
            upload_id=upload.pk,
            steam_id=upload.player_steam_id,
            status="ready" if upload.state == "ready" else "pending",
            report=upload.report,
            scripts=upload.scripts,
            selection=upload.selection,
        )
        Review.objects.using(alias).filter(upload_id=upload.pk).update(player_result_id=result.pk)
        Upload.objects.using(alias).filter(pk=upload.pk).update(
            report=None, scripts=None, selection=None
        )


def backwards(apps, schema_editor):
    Upload = apps.get_model("trainer", "Upload")
    Result = apps.get_model("trainer", "PlayerAnalysis")
    Review = apps.get_model("trainer", "PracticeReview")
    alias = schema_editor.connection.alias
    if Upload.objects.using(alias).filter(mode="team").exists():
        raise RuntimeError("Cannot roll back player results while team uploads exist")
    for result in Result.objects.using(alias).filter(upload__mode="individual").iterator():
        Upload.objects.using(alias).filter(pk=result.upload_id).update(
            report=result.report, scripts=result.scripts, selection=result.selection
        )
    Review.objects.using(alias).update(player_result_id=None)


class Migration(migrations.Migration):
    dependencies = [("trainer", "0011_playeranalysis_team_teammember_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
