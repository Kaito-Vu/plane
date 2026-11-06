"""Workspace assets live in bucket <workspace slug>, folder <project id>, without touching core views/storage.

Core builds keys as "<workspace_id>/<hex>-<name>". A pre_save hook rewrites new FileAsset keys to
"ws:<bucket>/<project_id|workspace>/<hex>-<name>"; S3Storage is patched to split that prefix into
(bucket, key). Unprefixed keys (user avatars, exports, legacy assets) keep using the default bucket.
"""

import re
from functools import wraps

from botocore.exceptions import ClientError
from django.db.models.signals import pre_save

from plane.db.models import FileAsset
from plane.settings.storage import S3Storage
from plane.utils.exception_logger import log_exception

PREFIX = "ws:"
LEGACY = re.compile(r"^([0-9a-f]{8}-[0-9a-f-]{27})/([0-9a-f]{32}-.*)$", re.S)
_KNOWN = set()  # ponytail: per-process cache, one head_bucket per bucket per worker


def bucket_name(slug):
    b = re.sub(r"[^a-z0-9-]", "-", str(slug).lower()).strip("-")  # S3: 3-63 chars, [a-z0-9-]
    return (b + "-ws")[:63] if len(b) < 3 else b[:63].strip("-")


def _rewrite(sender, instance, **kwargs):
    name = instance.asset.name if instance.asset else ""
    m = LEGACY.match(name or "")
    if not (instance._state.adding and instance.workspace_id and m and m.group(1) == str(instance.workspace_id)):
        return
    instance.asset.name = f"{PREFIX}{bucket_name(instance.workspace.slug)}/{instance.project_id or 'workspace'}/{m.group(2)}"


def _canon(name):
    """Map a legacy-shaped key handed out by core views to the rewritten key of its asset row."""
    name = str(name)
    m = LEGACY.match(name)
    if not m:
        return name
    row = FileAsset.objects.filter(workspace_id=m.group(1), asset__endswith=f"/{m.group(2)}", asset__startswith=PREFIX).first()
    return row.asset.name if row else name


def _split(self, name):
    name = str(name)
    if name.startswith(PREFIX):
        bucket, _, key = name[len(PREFIX) :].partition("/")
        return bucket, key
    return self.aws_storage_bucket_name, name


def _ensure(self, bucket):
    if bucket in _KNOWN or bucket == self.aws_storage_bucket_name:
        return
    try:
        self.s3_client.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket", "NotFound"):
            return log_exception(e)
        try:
            self.s3_client.create_bucket(Bucket=bucket)
        except ClientError as e2:
            return log_exception(e2)
    _KNOWN.add(bucket)


def _in_bucket(orig, canon=False, create=False):
    """Run an S3Storage method whose first arg is a key against that key's bucket (instances are per-request)."""

    @wraps(orig)
    def wrapper(self, object_name, *args, **kwargs):
        if canon:
            object_name = _canon(object_name)
        bucket, key = _split(self, object_name)
        if create:
            _ensure(self, bucket)
        default = self.aws_storage_bucket_name
        self.aws_storage_bucket_name = bucket
        try:
            return orig(self, key, *args, **kwargs)
        finally:
            self.aws_storage_bucket_name = default

    return wrapper


def install():
    pre_save.connect(_rewrite, sender=FileAsset, dispatch_uid="ee-workspace-bucket-key")
    S3Storage.generate_presigned_post = _in_bucket(S3Storage.generate_presigned_post, canon=True, create=True)
    S3Storage.upload_file = _in_bucket(S3Storage.upload_file, canon=True, create=True)
    S3Storage.generate_presigned_url = _in_bucket(S3Storage.generate_presigned_url)
    S3Storage.get_object_metadata = _in_bucket(S3Storage.get_object_metadata)

    orig_delete = S3Storage.delete_files

    @wraps(orig_delete)
    def delete_files(self, object_names):
        groups = {}
        for n in object_names:
            b, k = _split(self, n)
            groups.setdefault(b, []).append(k)
        default = self.aws_storage_bucket_name
        try:
            ok = True
            for b, keys in groups.items():
                self.aws_storage_bucket_name = b
                ok = orig_delete(self, keys) and ok
            return ok
        finally:
            self.aws_storage_bucket_name = default

    S3Storage.delete_files = delete_files

    orig_copy = S3Storage.copy_object

    @wraps(orig_copy)
    def copy_object(self, object_name, new_object_name):
        src_bucket, src_key = _split(self, object_name)
        dst_bucket, dst_key = _split(self, _canon(new_object_name))
        _ensure(self, dst_bucket)
        try:
            return self.s3_client.copy_object(
                Bucket=dst_bucket, CopySource={"Bucket": src_bucket, "Key": src_key}, Key=dst_key
            )
        except ClientError as e:
            log_exception(e)
            return None

    S3Storage.copy_object = copy_object
