import uuid

import pytest

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.db.models import Account, User
from plane.ee.entra_auth.entra import EntraProvider
from plane.ee.entra_auth.profile import claims_to_user_data

UNUSABLE = AUTHENTICATION_ERROR_CODES["ENTRA_EMAIL_UNUSABLE"]


def _provider(oid, email, domains):
    p = object.__new__(EntraProvider)
    p.allowed_domains = domains
    p.user_data = {"email": email, "user": {"provider_id": oid}}
    return p


def _user(email):
    return User.objects.create(email=email, username=uuid.uuid4().hex)


@pytest.mark.unit
@pytest.mark.django_db
class TestIdentity:
    def test_new_user_ok(self):
        _provider("oid-1", "new@etc.vn", []) ._check_identity()

    def test_link_existing_requires_domain_allowlist(self):
        _user("a@etc.vn")
        with pytest.raises(AuthenticationException) as e:
            _provider("oid-1", "a@etc.vn", [])._check_identity()
        assert e.value.error_code == UNUSABLE
        _provider("oid-1", "a@etc.vn", ["etc.vn"])._check_identity()

    def test_known_oid_with_changed_email_refused(self):
        u = _user("a@etc.vn")
        Account.objects.create(user=u, provider="entra", provider_account_id="oid-1")
        with pytest.raises(AuthenticationException):
            _provider("oid-1", "other@etc.vn", ["etc.vn"])._check_identity()
        _provider("oid-1", "a@etc.vn", [])._check_identity()

    def test_email_bound_to_other_oid_refused(self):
        u = _user("a@etc.vn")
        Account.objects.create(user=u, provider="entra", provider_account_id="oid-1")
        with pytest.raises(AuthenticationException):
            _provider("oid-2", "a@etc.vn", ["etc.vn"])._check_identity()


@pytest.mark.unit
@pytest.mark.parametrize("extra", [{"idp": "https://sts.windows.net/x/"}, {"preferred_username": "a_x.com#EXT#@etc.vn"}])
def test_guest_rejected(extra):
    with pytest.raises(AuthenticationException) as e:
        claims_to_user_data({"oid": "o", "email": "a@etc.vn", **extra}, [])
    assert e.value.error_code == UNUSABLE
