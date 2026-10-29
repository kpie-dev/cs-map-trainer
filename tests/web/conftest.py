import uuid
from unittest.mock import Mock

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from cs_map_trainer.web import services
from cs_map_trainer.web.models import SteamIdentity
from cs_map_trainer.web.storage import R2


@pytest.fixture
def user():
    user = get_user_model().objects.create_user("player", "player@example.test", "some-password")
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    SteamIdentity.objects.create(steam_id="76561198000000001", owner=user)
    return user


@pytest.fixture
def storage():
    storage = Mock(spec=R2)
    storage.begin.return_value = "multipart-id"
    storage.sign.return_value = "https://example.test/signed-upload"
    storage.orphans.return_value = []
    return storage


@pytest.fixture
def upload(user, storage):
    return services.initiate(user, uuid.uuid4(), 32, storage)


@pytest.fixture
def api(client, user):
    client.force_login(user)
    return client
