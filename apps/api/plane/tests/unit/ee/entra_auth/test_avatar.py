from unittest.mock import MagicMock, patch

import pytest
import requests

from plane.authentication.adapter.base import Adapter
from plane.db.models import FileAsset, User
from plane.ee.entra_auth.entra import EntraProvider
from plane.ee.entra_auth.profile import GRAPH_PHOTO_URL

pytestmark = pytest.mark.django_db


def resp(status=200, ctype="image/jpeg", body=b"\xff\xd8img", headers=None):
    r = MagicMock(status_code=status)
    r.headers = {"Content-Type": ctype, **(headers or {})}
    r.iter_content.return_value = [body]
    r.raise_for_status.side_effect = requests.HTTPError("x") if status >= 400 else None
    return r


def make(cls=EntraProvider, provider="entra", token="tok"):
    p = object.__new__(cls)
    p.provider = provider
    p.request = MagicMock()
    p.request.META = {}
    p.token_data = {"access_token": token}
    p.callback = None
    p.user_data = {
        "email": "a@x.com",
        "user": {"first_name": "New", "last_name": "", "avatar": GRAPH_PHOTO_URL},
    }
    return p


@pytest.fixture
def user():
    return User.objects.create(email="a@x.com", username="a", first_name="Old")


@pytest.fixture(autouse=True)
def storage():
    with patch("plane.authentication.adapter.base.S3Storage") as s:
        s.return_value.upload_file.return_value = True
        s.return_value.get_object_metadata.return_value = {}
        yield s


def test_graph_200_creates_asset(user):
    with patch("plane.ee.entra_auth.entra.pinned_fetch", return_value=resp()) as f:
        asset = make().download_and_upload_avatar(GRAPH_PHOTO_URL, user)
    assert isinstance(asset, FileAsset) and FileAsset.objects.filter(pk=asset.pk).exists()
    assert f.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert f.call_args.args[1] == GRAPH_PHOTO_URL


@pytest.mark.parametrize("effect", [resp(404), resp(403), resp(429), requests.Timeout("t"), resp(ctype="text/html")])
def test_failures_return_none(user, effect):
    kw = {"side_effect": effect} if isinstance(effect, Exception) else {"return_value": effect}
    with patch("plane.ee.entra_auth.entra.pinned_fetch", **kw):
        assert make().download_and_upload_avatar(GRAPH_PHOTO_URL, user) is None


def test_oversized_returns_none(user):
    with patch("plane.ee.entra_auth.entra.pinned_fetch", return_value=resp(headers={"Content-Length": str(10**9)})):
        assert make().download_and_upload_avatar(GRAPH_PHOTO_URL, user) is None


def test_other_url_never_fetched(user):
    with patch("plane.ee.entra_auth.entra.pinned_fetch") as f:
        assert make().download_and_upload_avatar("https://evil.example/x.jpg", user) is None
    f.assert_not_called()


def test_redirect_to_other_host_never_followed_and_no_token_leak(user):
    calls = []

    def fake_request(method, scheme, hostname, ip, port, path, *, headers, **kw):
        calls.append((hostname, headers))
        return resp(302, headers={"Location": "https://evil.example/steal"})

    with (
        patch("plane.utils.url_security.resolve_and_validate", return_value=["1.2.3.4"]),
        patch("plane.utils.url_security._request_to_ip", side_effect=fake_request),
    ):
        assert make().download_and_upload_avatar(GRAPH_PHOTO_URL, user) is None
    assert [h for h, _ in calls] == ["graph.microsoft.com"]
    assert all(h == "graph.microsoft.com" for h, hdr in calls if "Authorization" in hdr)


def test_failed_download_leaves_no_graph_url_on_user(user):
    user.avatar = GRAPH_PHOTO_URL
    p = make()
    p.request.META = {"REMOTE_ADDR": "1.1.1.1", "HTTP_USER_AGENT": "ua"}
    p.save_user_data(user)
    user.refresh_from_db()
    assert user.avatar == ""


def test_sync_404_keeps_existing_avatar(user):
    old = FileAsset.objects.create(
        asset="old.jpg", user=user, entity_type=FileAsset.EntityTypeContext.USER_AVATAR, attributes={"name": "o", "type": "image/jpeg", "size": 1}, size=1
    )
    user.avatar_asset = old
    user.save()
    with patch("plane.ee.entra_auth.entra.pinned_fetch", return_value=resp(404)):
        make().sync_user_data(user)
    user.refresh_from_db()
    assert user.avatar_asset_id == old.pk and user.first_name == "New"


def test_signup_with_asset_still_clears_graph_url(user):
    asset = FileAsset.objects.create(
        asset="n.jpg", user=user, entity_type=FileAsset.EntityTypeContext.USER_AVATAR, attributes={"name": "n", "type": "image/jpeg", "size": 1}, size=1
    )
    user.avatar_asset = asset
    user.avatar = GRAPH_PHOTO_URL
    p = make()
    p.request.META = {"REMOTE_ADDR": "1.1.1.1", "HTTP_USER_AGENT": "ua"}
    p.save_user_data(user)
    user.refresh_from_db()
    assert user.avatar == "" and user.avatar_asset_id == asset.pk


def test_sync_replaces_avatar_when_photo_exists(user):
    old = FileAsset.objects.create(
        asset="old.jpg", user=user, entity_type=FileAsset.EntityTypeContext.USER_AVATAR, attributes={"name": "o", "type": "image/jpeg", "size": 1}, size=1
    )
    user.avatar_asset = old
    user.save()
    with patch("plane.ee.entra_auth.entra.pinned_fetch", return_value=resp()):
        make().sync_user_data(user)
    user.refresh_from_db()
    assert user.avatar_asset_id is not None and user.avatar_asset_id != old.pk
    assert not FileAsset.objects.filter(pk=old.pk).exists()


def test_sync_flag_gates_existing_users():
    p = make()
    for val, expected in (("0", False), ("1", True)):
        with patch("plane.authentication.adapter.base.get_configuration_value", return_value=(val,)):
            assert p.check_sync_enabled() is expected


def test_github_still_uses_default_fetch_avatar(user):
    p = make(Adapter, provider="github")
    assert type(p).fetch_avatar is Adapter.fetch_avatar
    with patch("plane.authentication.adapter.base.pinned_fetch_following_redirects", return_value=(resp(), "u")) as f:
        assert p.download_and_upload_avatar("https://avatars.githubusercontent.com/u/1", user) is not None
    assert f.call_args.kwargs == {"headers": {}, "timeout": 10, "max_redirects": 5, "stream": True}
