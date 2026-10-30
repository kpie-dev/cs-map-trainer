import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class InvalidUpload(ValueError):
    pass


class R2:
    def __init__(self):
        if not all(
            (
                settings.R2_ENDPOINT,
                settings.R2_BUCKET,
                settings.R2_ACCESS_KEY_ID,
                settings.R2_SECRET_ACCESS_KEY,
            )
        ):
            raise ImproperlyConfigured("Configure the private R2 bucket and credentials")
        self.bucket = settings.R2_BUCKET
        self.client = self._client(settings.R2_ENDPOINT)
        self.upload_client = (
            self._client(settings.R2_PUBLIC_ENDPOINT)
            if settings.R2_PUBLIC_ENDPOINT
            else self.client
        )

    @staticmethod
    def _client(endpoint):
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=30,
                retries={"max_attempts": 1},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def begin(self, upload):
        return self.client.create_multipart_upload(
            Bucket=self.bucket, Key=upload.key, ContentType="application/octet-stream"
        )["UploadId"]

    def sign(self, upload):
        return self.upload_client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": upload.key,
                "UploadId": upload.multipart_id,
                "PartNumber": 1,
                "ContentLength": upload.size_bytes,
            },
            ExpiresIn=settings.UPLOAD_URL_SECONDS,
        )

    def complete(self, upload):
        parts = self.client.list_parts(
            Bucket=self.bucket, Key=upload.key, UploadId=upload.multipart_id
        )
        values = parts.get("Parts", [])
        if (
            parts.get("IsTruncated")
            or len(values) != 1
            or values[0]["PartNumber"] != 1
            or values[0]["Size"] != upload.size_bytes
        ):
            raise InvalidUpload("Upload must contain exactly one part of the reserved size")
        self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=upload.key,
            UploadId=upload.multipart_id,
            MultipartUpload={"Parts": [{"PartNumber": 1, "ETag": values[0]["ETag"]}]},
        )
        self.verify(upload)

    def verify(self, upload):
        result = self.client.head_object(Bucket=self.bucket, Key=upload.key)
        if result["ContentLength"] != upload.size_bytes:
            raise InvalidUpload("Stored object size differs from the reservation")

    def download(self, upload, path):
        started = time.monotonic()
        result = self.client.get_object(Bucket=self.bucket, Key=upload.key)
        body = result["Body"]
        with body, path.open("xb") as target:
            if result["ContentLength"] != upload.size_bytes:
                raise InvalidUpload("Stored object size differs from the reservation")
            total = 0
            for block in body.iter_chunks(chunk_size=1024**2):
                total += len(block)
                if total > upload.size_bytes:
                    raise InvalidUpload("Download exceeded the reserved size")
                if time.monotonic() - started > 300:
                    raise TimeoutError("Demo download timed out")
                target.write(block)
        if total != upload.size_bytes:
            raise InvalidUpload("Incomplete demo download")

    def delete(self, upload):
        if upload.multipart_id:
            try:
                self.client.abort_multipart_upload(
                    Bucket=self.bucket, Key=upload.key, UploadId=upload.multipart_id
                )
            except ClientError as error:
                if error.response["Error"]["Code"] != "NoSuchUpload":
                    raise
        self.client.delete_object(Bucket=self.bucket, Key=upload.key)

    def orphans(self, cutoff):
        for page in self.client.get_paginator("list_multipart_uploads").paginate(
            Bucket=self.bucket, Prefix="inputs/"
        ):
            for item in page.get("Uploads", []):
                if item["Initiated"] < cutoff:
                    yield {"key": item["Key"], "multipart_id": item["UploadId"]}
        for page in self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix="inputs/"
        ):
            for item in page.get("Contents", []):
                if item["LastModified"] < cutoff:
                    yield {"key": item["Key"], "multipart_id": ""}

    def delete_orphan(self, item):
        from types import SimpleNamespace

        self.delete(SimpleNamespace(**item))
