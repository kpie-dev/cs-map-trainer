from django.db import migrations
from django.db.models import F
from django.db.models.functions import JSONObject


def minimize_steam_profiles(apps, schema_editor):
    account = apps.get_model("socialaccount", "SocialAccount")
    account.objects.using(schema_editor.connection.alias).filter(provider="steam").update(
        extra_data=JSONObject(steamid=F("uid"))
    )


class Migration(migrations.Migration):
    dependencies = [
        ("trainer", "0001_initial"),
        ("socialaccount", "0006_alter_socialaccount_extra_data"),
    ]

    operations = [migrations.RunPython(minimize_steam_profiles, migrations.RunPython.noop)]
