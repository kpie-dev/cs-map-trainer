import json
import os
import subprocess
import sys

import pytest
from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, override_settings


def load_security_settings(**environment):
    env = {
        **os.environ,
        "DJANGO_SECRET_KEY": "deployment-settings-test-only",
        "DJANGO_DEBUG": "0",
        "DJANGO_TRUST_PROXY": "0",
        **environment,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from cs_map_trainer.web import settings as s; "
            "print(json.dumps({key: getattr(s, key) for key in "
            "['DEBUG', 'SECURE_SSL_REDIRECT', 'SECURE_PROXY_SSL_HEADER', "
            "'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE']}))",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_production_settings_require_explicit_proxy_trust():
    settings = load_security_settings()
    assert settings == {
        "DEBUG": False,
        "SECURE_SSL_REDIRECT": True,
        "SECURE_PROXY_SSL_HEADER": None,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
    }
    settings = load_security_settings(DJANGO_TRUST_PROXY="1")
    assert settings["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]


def test_local_http_settings_remain_supported():
    settings = load_security_settings(DJANGO_DEBUG="1")
    assert settings["DEBUG"]
    assert not settings["SECURE_SSL_REDIRECT"]
    assert not settings["SESSION_COOKIE_SECURE"]
    assert not settings["CSRF_COOKIE_SECURE"]
    assert settings["SECURE_PROXY_SSL_HEADER"] is None


@pytest.mark.parametrize(
    ("trust_proxy", "forwarded_proto", "status"),
    [(False, "https", 301), (True, "http", 301), (True, "https", 200)],
)
def test_tls_proxy_does_not_loop_and_untrusted_headers_cannot_disable_redirect(
    trust_proxy, forwarded_proto, status
):
    with override_settings(
        ALLOWED_HOSTS=["trainer.example"],
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https") if trust_proxy else None,
    ):
        request = RequestFactory().get(
            "/accounts/login/",
            HTTP_HOST="trainer.example",
            HTTP_X_FORWARDED_PROTO=forwarded_proto,
        )
        response = SecurityMiddleware(lambda request: HttpResponse("ok"))(request)
        assert response.status_code == status
        if status == 301:
            assert response["Location"] == "https://trainer.example/accounts/login/"
