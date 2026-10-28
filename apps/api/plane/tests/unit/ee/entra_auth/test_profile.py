import pytest

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.entra_auth.profile import GRAPH_PHOTO_URL, claims_to_user_data, parse_domains


def _code(exc):
    return exc.value.error_code


@pytest.mark.unit
class TestProfile:
    def test_happy_path(self):
        d = claims_to_user_data({"oid": "o1", "email": "Alice@ETC.vn", "name": "Alice"}, [])
        assert d["email"] == "alice@etc.vn"
        u = d["user"]
        assert u["provider_id"] == "o1" and u["email"] == "alice@etc.vn"
        assert u["first_name"] == "Alice" and u["last_name"] == ""
        assert u["avatar"] == GRAPH_PHOTO_URL and u["is_password_autoset"] is True

    def test_preferred_username_fallback(self):
        assert claims_to_user_data({"oid": "o", "preferred_username": "a@etc.vn"}, [])["email"] == "a@etc.vn"

    def test_unusable_email(self):
        with pytest.raises(AuthenticationException) as e:
            claims_to_user_data({"oid": "o", "preferred_username": "a-user"}, [])
        assert _code(e) == AUTHENTICATION_ERROR_CODES["ENTRA_EMAIL_UNUSABLE"]

    def test_domain_allowlist(self):
        c = {"oid": "o", "email": "x@other.com"}
        with pytest.raises(AuthenticationException) as e:
            claims_to_user_data(c, ["etc.vn"])
        assert _code(e) == AUTHENTICATION_ERROR_CODES["ENTRA_EMAIL_UNUSABLE"]
        assert claims_to_user_data(c, [])["email"] == "x@other.com"

    def test_missing_oid(self):
        with pytest.raises(AuthenticationException) as e:
            claims_to_user_data({"email": "a@etc.vn"}, [])
        assert _code(e) == AUTHENTICATION_ERROR_CODES["ENTRA_PROVIDER_ERROR"]

    def test_missing_name(self):
        assert claims_to_user_data({"oid": "o", "email": "bob@etc.vn"}, [])["user"]["first_name"] == "bob"

    def test_padded_email(self):
        assert claims_to_user_data({"oid": "o", "email": "  Alice@ETC.vn "}, [])["email"] == "alice@etc.vn"

    def test_invalid_email_falls_back_to_preferred_username(self):
        d = claims_to_user_data({"oid": "o", "email": "nope", "preferred_username": "a@etc.vn"}, [])
        assert d["email"] == "a@etc.vn"

    def test_empty_oid(self):
        with pytest.raises(AuthenticationException) as e:
            claims_to_user_data({"oid": "", "email": "a@etc.vn"}, [])
        assert _code(e) == AUTHENTICATION_ERROR_CODES["ENTRA_PROVIDER_ERROR"]

    def test_lookalike_domain_rejected(self):
        with pytest.raises(AuthenticationException) as e:
            claims_to_user_data({"oid": "o", "email": "x@evil-etc.vn"}, ["etc.vn"])
        assert _code(e) == AUTHENTICATION_ERROR_CODES["ENTRA_EMAIL_UNUSABLE"]

    def test_whitespace_name_falls_back(self):
        assert claims_to_user_data({"oid": "o", "email": "bob@etc.vn", "name": "  "}, [])["user"]["first_name"] == "bob"

    def test_parse_domains(self):
        assert parse_domains(" ETC.vn, ,a.com ") == ["etc.vn", "a.com"]
        assert parse_domains(None) == []
