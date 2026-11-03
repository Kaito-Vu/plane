import re
from collections.abc import Mapping, Sequence
from typing import Any

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException

GRAPH_PHOTO_URL = "https://graph.microsoft.com/v1.0/me/photo/$value"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_domains(raw: str | None) -> list[str]:
    return [d for d in (p.strip().lstrip("@").lower() for p in (raw or "").split(",")) if d]


def _error(name: str) -> AuthenticationException:
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[name], error_message=name)


def claims_to_user_data(claims: Mapping[str, Any], allowed_domains: Sequence[str]) -> dict:
    oid = claims.get("oid")
    if not oid:
        raise _error("ENTRA_PROVIDER_ERROR")

    # B2B guests: their email comes from a directory we do not control (idp is only present for them)
    upn = claims.get("preferred_username")
    if claims.get("idp") or (isinstance(upn, str) and "#EXT#" in upn):
        raise _error("ENTRA_EMAIL_UNUSABLE")

    email = None
    for key in ("email", "preferred_username"):
        value = claims.get(key)
        value = value.strip().lower() if isinstance(value, str) else ""
        if _EMAIL_RE.match(value):
            email = value
            break
    if not email:
        raise _error("ENTRA_EMAIL_UNUSABLE")
    if allowed_domains and email.rsplit("@", 1)[1] not in allowed_domains:
        raise _error("ENTRA_EMAIL_UNUSABLE")

    return {
        "email": email,
        "user": {
            "provider_id": oid,
            "email": email,
            "avatar": GRAPH_PHOTO_URL,
            "first_name": (claims["name"].strip() if isinstance(claims.get("name"), str) else "") or email.split("@")[0],
            "last_name": "",
            "is_password_autoset": True,
        },
    }
