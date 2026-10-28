"""Opt-in contract probe; uses only a generated synthetic payload in a private input bucket."""

import os
import uuid
from types import SimpleNamespace

import pytest
import requests
from botocore.exceptions import ClientError

from cs_map_trainer.web.storage import R2


@pytest.mark.skipif(
    os.environ.get("CS_MAP_TRAINER_R2_CONTRACT") != "1",
    reason="Requires an explicitly configured private R2 contract-test bucket",
)
def test_r2_signed_size_completion_and_revocation(settings, tmp_path):
    for name in ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        setattr(settings, name, os.environ[name])
    storage = R2()
    payload = b"PBDEMS2\x00" + b"\x00" * 24
    upload = SimpleNamespace(
        key=f"inputs/contract-{uuid.uuid4()}.dem",
        multipart_id="",
        size_bytes=len(payload),
    )
    try:
        upload.multipart_id = storage.begin(upload)
        url = storage.sign(upload)
        rejected = requests.put(url, data=payload + b"x", timeout=30)
        assert rejected.status_code == 403
        accepted = requests.put(url, data=payload, timeout=30)
        accepted.raise_for_status()
        storage.complete(upload)
        target = tmp_path / "input.dem"
        storage.download(upload, target)
        assert target.read_bytes() == payload
        replay = requests.put(url, data=payload, timeout=30)
        assert replay.status_code in (400, 404)
    finally:
        storage.delete(upload)
    with pytest.raises(ClientError) as error:
        storage.verify(upload)
    assert error.value.response["ResponseMetadata"]["HTTPStatusCode"] == 404
