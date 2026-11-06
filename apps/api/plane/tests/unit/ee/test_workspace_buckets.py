import pytest

from plane.ee.workspace_buckets import LEGACY, bucket_name


@pytest.mark.unit
def test_bucket_name_follows_s3_rules():
    assert bucket_name("My_Team") == "my-team"
    assert bucket_name("ab") == "ab-ws"


@pytest.mark.unit
def test_legacy_key_shape():
    wid = "12345678-1234-1234-1234-123456789abc"
    assert LEGACY.match(f"{wid}/{'a' * 32}-x.png")
    assert not LEGACY.match("user_info/avatar/" + "a" * 32 + "-x.png")
