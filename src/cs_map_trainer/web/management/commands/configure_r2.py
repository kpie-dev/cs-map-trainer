from django.core.management.base import BaseCommand

from cs_map_trainer.web.storage import R2


class Command(BaseCommand):
    help = "Configure CORS and safety expiry on a DEDICATED private demo-input bucket."

    def add_arguments(self, parser):
        parser.add_argument("--origin", required=True)

    def handle(self, *args, **options):
        storage = R2()
        storage.client.put_bucket_cors(
            Bucket=storage.bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": [options["origin"]],
                        "AllowedMethods": ["PUT"],
                        "AllowedHeaders": ["content-type"],
                        "ExposeHeaders": ["ETag"],
                        "MaxAgeSeconds": 300,
                    }
                ]
            },
        )
        storage.client.put_bucket_lifecycle_configuration(
            Bucket=storage.bucket,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "expire-demo-inputs",
                        "Status": "Enabled",
                        "Filter": {"Prefix": "inputs/"},
                        "Expiration": {"Days": 1},
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                    }
                ]
            },
        )
        self.stdout.write("Configured input expiry and CORS; public access must remain disabled.")
