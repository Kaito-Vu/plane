# EE SSO Plugin — Phase 1: Backend OIDC / Azure AD / OAuth2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-contained Django app `plane.ee` that adds OIDC, Azure AD and generic OAuth2 sign-in to the API without editing any upstream core file.

**Architecture:** One OAuth adapter (`SsoOauthProvider`, subclass of core `OauthAdapter`) serves three provider ids (`oidc`, `azure_ad`, `oauth2`); Azure AD is an OIDC preset (issuer derived from tenant id). Config lives in core `InstanceConfiguration` rows seeded by the plugin on `post_migrate`, so the existing core `PATCH /api/instances/configurations/` already edits them (no custom config endpoint needed). The plugin is enabled by `DJANGO_SETTINGS_MODULE=plane.settings.ee`, which extends production settings and swaps `ROOT_URLCONF` for `plane.ee.urls` (core urlpatterns + `/auth/sso/`).

**Tech Stack:** Django 5.2, DRF, PyJWT 2.13 (already in `requirements/base.txt`), `requests`, pytest / pytest-django / pytest-mock.

**Spec:** `docs/superpowers/specs/2026-10-01-ee-sso-plugin-design.md`

**Out of this plan (own plans later):** Phase 2 SAML, Phase 3 web/space login buttons, Phase 4 admin pages, Phase 5 Docker/compose wiring.

**Spec deltas decided while planning** (update spec after Phase 1 lands): (a) no EE admin config endpoint — core configurations endpoint is reused because keys are seeded; (b) flat module layout `plane/ee/sso/*.py` instead of `providers/`.

## Global Constraints

- No file under `apps/api/plane/` that exists upstream may be modified. Only add files.
- Every new `.py` file starts with the 3-line header used in core: `# Copyright (c) 2023-present Plane Software, Inc. and contributors` / `# SPDX-License-Identifier: AGPL-3.0-only` / `# See the LICENSE file for details.`
- Provider ids: `oidc`, `azure_ad`, `oauth2` (`saml` reserved for Phase 2). Account.provider stored as `sso-<id>`.
- Config keys: `EE_SSO_<PROVIDER_ID_UPPER>_<FIELD>`; `CLIENT_SECRET` is `is_encrypted=True`.
- Error codes 6000-6099 reserved for the plugin.
- Verified email only: reject when `email_verified` is present and false.
- Tests run in Docker: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test <path>` (run `./setup.sh` once first).

## File Structure

```
apps/api/plane/settings/ee.py                 # prod settings + plugin
apps/api/plane/settings/ee_test.py            # test settings + plugin
apps/api/plane/ee/__init__.py
apps/api/plane/ee/apps.py                     # AppConfig: registers errors, seeds config post_migrate
apps/api/plane/ee/urls.py                     # core urlpatterns + auth/sso/
apps/api/plane/ee/sso/__init__.py
apps/api/plane/ee/sso/errors.py               # error codes
apps/api/plane/ee/sso/config.py               # keys, seeding, get_sso_config, list_enabled_providers
apps/api/plane/ee/sso/oidc.py                 # discovery + id_token verification
apps/api/plane/ee/sso/adapter.py              # SsoOauthProvider
apps/api/plane/ee/sso/flow.py                 # shared helpers: redirect_error, provider_error, complete_login
apps/api/plane/ee/sso/views.py                # providers list, initiate, callback
apps/api/plane/ee/sso/urls.py
apps/api/plane/tests/unit/ee/__init__.py
apps/api/plane/tests/unit/ee/sso/__init__.py
apps/api/plane/tests/unit/ee/sso/conftest.py  # RSA key + id_token helper
apps/api/plane/tests/unit/ee/sso/test_*.py
```

---

### Task 1: Plugin skeleton and settings

**Files:**

- Create: `apps/api/plane/settings/ee.py`, `apps/api/plane/settings/ee_test.py`
- Create: `apps/api/plane/ee/__init__.py`, `apps/api/plane/ee/apps.py`, `apps/api/plane/ee/urls.py`
- Create: `apps/api/plane/ee/sso/__init__.py`, `apps/api/plane/ee/sso/errors.py`
- Create: `apps/api/plane/tests/unit/ee/__init__.py`, `apps/api/plane/tests/unit/ee/sso/__init__.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_skeleton.py`

**Interfaces:**

- Produces: `plane.ee.sso.errors.EE_SSO_ERROR_CODES` (dict) registered into `AUTHENTICATION_ERROR_CODES` with keys `SSO_NOT_CONFIGURED=6000`, `SSO_PROVIDER_ERROR=6001`, `SSO_PROVIDER_UNVERIFIED_EMAIL=6002`.
- Produces: `plane.ee.apps.EeConfig` (label `ee`); `plane.ee.urls.urlpatterns` and `handler404`.
- Produces: settings modules `plane.settings.ee`, `plane.settings.ee_test`.

- [ ] **Step 1: Create empty package files** (`ee/__init__.py`, `ee/sso/__init__.py`, `tests/unit/ee/__init__.py`, `tests/unit/ee/sso/__init__.py`) containing only the license header.

- [ ] **Step 2: Write the failing test** `plane/tests/unit/ee/sso/test_skeleton.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.apps import apps
from django.conf import settings

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES


@pytest.mark.unit
def test_plugin_installed_and_urlconf_swapped():
    assert apps.is_installed("plane.ee")
    assert settings.ROOT_URLCONF == "plane.ee.urls"


@pytest.mark.unit
def test_error_codes_registered():
    assert AUTHENTICATION_ERROR_CODES["SSO_NOT_CONFIGURED"] == 6000
    assert AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_ERROR"] == 6001
    assert AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_UNVERIFIED_EMAIL"] == 6002
```

- [ ] **Step 3: Run, expect FAIL** (`ModuleNotFoundError: plane.settings.ee_test`)

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_skeleton.py`

- [ ] **Step 4: Implement**

`plane/settings/ee.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Production settings + EE plugin. Enable with DJANGO_SETTINGS_MODULE=plane.settings.ee"""

from .production import *  # noqa

INSTALLED_APPS = [*INSTALLED_APPS, "plane.ee"]  # noqa
ROOT_URLCONF = "plane.ee.urls"
```

`plane/settings/ee_test.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Test settings + EE plugin."""

from .test import *  # noqa

INSTALLED_APPS = [*INSTALLED_APPS, "plane.ee"]  # noqa
ROOT_URLCONF = "plane.ee.urls"
```

`plane/ee/sso/errors.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES

EE_SSO_ERROR_CODES = {
    "SSO_NOT_CONFIGURED": 6000,
    "SSO_PROVIDER_ERROR": 6001,
    "SSO_PROVIDER_UNVERIFIED_EMAIL": 6002,
}

# Register into the core dict so AuthenticationException lookups work unchanged.
AUTHENTICATION_ERROR_CODES.update(EE_SSO_ERROR_CODES)
```

`plane/ee/apps.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig


class EeConfig(AppConfig):
    name = "plane.ee"
    label = "ee"

    def ready(self):
        from plane.ee.sso import errors  # noqa: F401  (registers error codes)
```

Set in `plane/ee/__init__.py` (after the header): `default_app_config` is not needed in Django 5; Django auto-detects the single AppConfig in `apps.py`.

`plane/ee/urls.py` (the sso include is added in Task 5; for now only core):

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.urls import handler404, urlpatterns as core_urlpatterns  # noqa: F401

urlpatterns = [*core_urlpatterns]
```

- [ ] **Step 5: Run, expect PASS** (same command).

- [ ] **Step 6: Commit**

```bash
git add apps/api/plane/settings/ee.py apps/api/plane/settings/ee_test.py apps/api/plane/ee apps/api/plane/tests/unit/ee
git commit -m "feat(ee): add EE plugin skeleton and settings"
```

---

### Task 2: SSO config (keys, seeding, lookup)

**Files:**

- Create: `apps/api/plane/ee/sso/config.py`
- Modify: `apps/api/plane/ee/apps.py` (connect `post_migrate`)
- Test: `apps/api/plane/tests/unit/ee/sso/test_config.py`

**Interfaces:**

- Produces:
  - `PROVIDERS: dict[str, {"label","protocol","fields","required"}]` and `PROVIDER_IDS: tuple[str, ...] = ("oidc", "azure_ad", "oauth2")` (Phase 2 appends `saml`)
  - `config_key(provider_id: str, field: str) -> str`
  - `seed_config() -> None` (idempotent get_or_create of all keys)
  - `get_sso_config(provider_id: str) -> dict | None` — dict keyed by field name (`CLIENT_ID`, `CLIENT_SECRET`, `LABEL`, plus provider specific fields, `SCOPE` defaulted); `None` if unknown id, not `ENABLED == "1"`, or any required field empty.
  - `list_enabled_providers() -> list[dict]` — `[{"id", "label", "protocol"}]`; `protocol` is `"oidc"` for `oidc`/`azure_ad`, `"oauth2"` for `oauth2`.

- [ ] **Step 1: Write the failing test** `test_config.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.ee.sso.config import (
    PROVIDERS,
    config_key,
    get_sso_config,
    list_enabled_providers,
    seed_config,
)
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data


def _set(provider, field, value, encrypted=False):
    row = InstanceConfiguration.objects.get(key=config_key(provider, field))
    row.value = encrypt_data(value) if encrypted else value
    row.save()


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_is_idempotent_and_marks_secret_encrypted():
    seed_config()
    seed_config()
    expected = sum(2 + len(p["fields"]) for p in PROVIDERS.values())  # ENABLED + LABEL + extras
    assert InstanceConfiguration.objects.filter(key__startswith="EE_SSO_").count() == expected
    assert InstanceConfiguration.objects.get(key="EE_SSO_OIDC_CLIENT_SECRET").is_encrypted is True
    assert InstanceConfiguration.objects.get(key="EE_SSO_OIDC_CLIENT_ID").is_encrypted is False


@pytest.mark.unit
@pytest.mark.django_db
def test_disabled_or_incomplete_returns_none():
    seed_config()
    assert get_sso_config("oidc") is None
    _set("oidc", "ENABLED", "1")
    _set("oidc", "CLIENT_ID", "cid")
    assert get_sso_config("oidc") is None  # secret + issuer missing
    assert get_sso_config("nope") is None


@pytest.mark.unit
@pytest.mark.django_db
def test_enabled_oidc_decrypts_secret_and_lists():
    seed_config()
    _set("oidc", "ENABLED", "1")
    _set("oidc", "LABEL", "ETC SSO")
    _set("oidc", "CLIENT_ID", "cid")
    _set("oidc", "CLIENT_SECRET", "sek", encrypted=True)
    _set("oidc", "ISSUER", "https://idp.example.com")
    cfg = get_sso_config("oidc")
    assert cfg["CLIENT_SECRET"] == "sek"
    assert cfg["SCOPE"] == "openid email profile"
    assert list_enabled_providers() == [{"id": "oidc", "label": "ETC SSO", "protocol": "oidc"}]


@pytest.mark.unit
@pytest.mark.django_db
def test_default_label_when_blank():
    seed_config()
    for f, v in [("ENABLED", "1"), ("CLIENT_ID", "c"), ("TENANT_ID", "t")]:
        _set("azure_ad", f, v)
    _set("azure_ad", "CLIENT_SECRET", "s", encrypted=True)
    assert list_enabled_providers()[0]["label"] == "Microsoft"
```

(20 keys: 5 common per provider x 3, plus ISSUER, TENANT_ID, AUTH_URL, TOKEN_URL, USERINFO_URL.)

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.config`).

- [ ] **Step 3: Implement** `config.py`.

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.license.models import InstanceConfiguration
from plane.license.utils.instance_value import get_configuration_value

DEFAULT_SCOPE = "openid email profile"
OAUTH_FIELDS = ["CLIENT_ID", "CLIENT_SECRET", "SCOPE"]
ENCRYPTED_FIELDS = {"CLIENT_SECRET"}

# Every provider also has ENABLED and LABEL (see BASE_FIELDS). `fields` are the provider-specific
# extras; `required` must all be non-empty for the provider to count as configured. Phase 2 adds "saml".
PROVIDERS = {
    "oidc": {
        "label": "OpenID Connect",
        "protocol": "oidc",
        "fields": [*OAUTH_FIELDS, "ISSUER"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "ISSUER"],
    },
    "azure_ad": {
        "label": "Microsoft",
        "protocol": "oidc",
        "fields": [*OAUTH_FIELDS, "TENANT_ID"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"],
    },
    "oauth2": {
        "label": "OAuth2",
        "protocol": "oauth2",
        "fields": [*OAUTH_FIELDS, "AUTH_URL", "TOKEN_URL", "USERINFO_URL"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "AUTH_URL", "TOKEN_URL", "USERINFO_URL"],
    },
}
PROVIDER_IDS = tuple(PROVIDERS)
BASE_FIELDS = ["ENABLED", "LABEL"]


def config_key(provider_id, field):
    return f"EE_SSO_{provider_id.upper()}_{field}"


def _fields(provider_id):
    return BASE_FIELDS + PROVIDERS[provider_id]["fields"]


def seed_config(**_kwargs):
    for provider_id in PROVIDER_IDS:
        for field in _fields(provider_id):
            InstanceConfiguration.objects.get_or_create(
                key=config_key(provider_id, field),
                defaults={
                    "value": "0" if field == "ENABLED" else "",
                    "category": f"EE_SSO_{provider_id.upper()}",
                    "is_encrypted": field in ENCRYPTED_FIELDS,
                },
            )


def get_sso_config(provider_id):
    if provider_id not in PROVIDERS:
        return None
    fields = _fields(provider_id)
    values = get_configuration_value([{"key": config_key(provider_id, f), "default": ""} for f in fields])
    cfg = dict(zip(fields, values))
    if cfg["ENABLED"] != "1":
        return None
    if not all(cfg.get(f) for f in PROVIDERS[provider_id]["required"]):
        return None
    if "SCOPE" in cfg:
        cfg["SCOPE"] = cfg["SCOPE"] or DEFAULT_SCOPE
    cfg["LABEL"] = cfg["LABEL"] or PROVIDERS[provider_id]["label"]
    return cfg


def list_enabled_providers():
    out = []
    for provider_id in PROVIDER_IDS:
        cfg = get_sso_config(provider_id)
        if cfg:
            out.append({"id": provider_id, "label": cfg["LABEL"], "protocol": PROVIDERS[provider_id]["protocol"]})
    return out
```

Connect seeding in `apps.py` `ready()` (append):

```python
        from django.db.models.signals import post_migrate

        from plane.ee.sso.config import seed_config

        # plane.ee has no models, so post_migrate is not emitted for it; hook on the
        # license app (owner of InstanceConfiguration) instead. seed_config is idempotent.
        post_migrate.connect(_seed_on_license_migrate, dispatch_uid="ee_sso_seed")
```

and module-level:

```python
def _seed_on_license_migrate(sender, **kwargs):
    if sender.label == "license":
        from plane.ee.sso.config import seed_config

        seed_config()
```

(Remove the unused `seed_config` import inside `ready`.)

- [ ] **Step 4: Run, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_config.py`

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee apps/api/plane/tests/unit/ee
git commit -m "feat(ee): SSO config keys, seeding and lookup"
```

---

### Task 3: OIDC discovery and id_token verification

**Files:**

- Create: `apps/api/plane/ee/sso/oidc.py`
- Create: `apps/api/plane/tests/unit/ee/sso/conftest.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_oidc.py`

**Interfaces:**

- Produces:
  - `discover(issuer: str) -> dict` — GET `{issuer}/.well-known/openid-configuration` (10s timeout, cached 1h); raises `AuthenticationException(SSO_PROVIDER_ERROR)` on HTTP error or when `meta["issuer"] != issuer`.
  - `verify_id_token(id_token: str, jwks_uri: str, issuer: str, audience: str, nonce: str) -> dict` — returns claims; raises `AuthenticationException(SSO_PROVIDER_ERROR)` on any signature / `iss` / `aud` / `exp` / `nonce` failure. Allowed algs `RS256`, `ES256`.
  - `_signing_key(jwks_uri, id_token)` — thin wrapper over `PyJWKClient` (the test patch point).
- conftest produces fixtures `rsa_keys` (private/public PEM) and `make_id_token(**claims_override) -> str` signed RS256, defaults `iss="https://idp.example.com"`, `aud="cid"`, `sub="u1"`, `nonce="n1"`, `email="a@b.com"`, `exp=now+300`; and autouse fixture patching `plane.ee.sso.oidc._signing_key` to return the public key, and clearing the cache.

- [ ] **Step 1: conftest.py**

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache


@pytest.fixture(scope="session")
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return private, key.public_key()


@pytest.fixture(autouse=True)
def _patch_jwks(mocker, rsa_keys):
    cache.clear()
    mocker.patch("plane.ee.sso.oidc._signing_key", return_value=rsa_keys[1])


@pytest.fixture
def make_id_token(rsa_keys):
    def _make(**override):
        claims = {
            "iss": "https://idp.example.com",
            "aud": "cid",
            "sub": "u1",
            "nonce": "n1",
            "email": "a@b.com",
            "exp": int(time.time()) + 300,
        }
        claims.update(override)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, rsa_keys[0], algorithm="RS256")

    return _make
```

- [ ] **Step 2: Failing tests** `test_oidc.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.authentication.adapter.error import AuthenticationException
from plane.ee.sso.oidc import discover, verify_id_token

ISS = "https://idp.example.com"


def _verify(token, **kw):
    args = {"jwks_uri": f"{ISS}/jwks", "issuer": ISS, "audience": "cid", "nonce": "n1"}
    args.update(kw)
    return verify_id_token(token, **args)


@pytest.mark.unit
def test_valid_token_returns_claims(make_id_token):
    assert _verify(make_id_token())["email"] == "a@b.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "override, kw",
    [
        ({"exp": 1}, {}),  # expired
        ({"aud": "other"}, {}),  # wrong audience
        ({"iss": "https://evil.example.com"}, {}),  # wrong issuer
        ({"nonce": "zzz"}, {}),  # nonce mismatch
        ({"nonce": None}, {}),  # nonce missing
    ],
)
def test_invalid_claims_rejected(make_id_token, override, kw):
    with pytest.raises(AuthenticationException):
        _verify(make_id_token(**override), **kw)


@pytest.mark.unit
def test_garbage_token_rejected():
    with pytest.raises(AuthenticationException):
        _verify("not.a.jwt")


@pytest.mark.unit
def test_discover_ok_and_cached(mocker):
    get = mocker.patch("plane.ee.sso.oidc.requests.get")
    get.return_value.json.return_value = {"issuer": ISS, "jwks_uri": f"{ISS}/jwks"}
    assert discover(ISS)["jwks_uri"] == f"{ISS}/jwks"
    discover(ISS)
    assert get.call_count == 1


@pytest.mark.unit
def test_discover_issuer_mismatch_rejected(mocker):
    get = mocker.patch("plane.ee.sso.oidc.requests.get")
    get.return_value.json.return_value = {"issuer": "https://other", "jwks_uri": "x"}
    with pytest.raises(AuthenticationException):
        discover(ISS)
```

- [ ] **Step 3: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.oidc`).

- [ ] **Step 4: Implement** `oidc.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import jwt
import requests
from django.core.cache import cache

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.sso import errors  # noqa: F401  (ensures codes are registered)

ALLOWED_ALGS = ["RS256", "ES256"]
DISCOVERY_TTL = 60 * 60


def _provider_error(message):
    return AuthenticationException(
        error_code=AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_ERROR"],
        error_message=f"SSO_PROVIDER_ERROR: {message}",
    )


def discover(issuer):
    cache_key = f"ee_sso_discovery:{issuer}"
    meta = cache.get(cache_key)
    if meta:
        return meta
    try:
        response = requests.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
        response.raise_for_status()
        meta = response.json()
    except (requests.RequestException, ValueError):
        raise _provider_error("discovery failed")
    # OIDC Discovery §4.3: issuer in metadata must match the one used to fetch it.
    if meta.get("issuer") != issuer:
        raise _provider_error("issuer mismatch")
    cache.set(cache_key, meta, DISCOVERY_TTL)
    return meta


def _signing_key(jwks_uri, id_token):
    return jwt.PyJWKClient(jwks_uri, timeout=10).get_signing_key_from_jwt(id_token).key


def verify_id_token(id_token, jwks_uri, issuer, audience, nonce):
    try:
        claims = jwt.decode(
            id_token,
            _signing_key(jwks_uri, id_token),
            algorithms=ALLOWED_ALGS,
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError:
        raise _provider_error("invalid id_token")
    if not nonce or claims.get("nonce") != nonce:
        raise _provider_error("nonce mismatch")
    return claims
```

- [ ] **Step 5: Run, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_oidc.py`

- [ ] **Step 6: Commit**

```bash
git add apps/api/plane/ee/sso/oidc.py apps/api/plane/tests/unit/ee/sso
git commit -m "feat(ee): OIDC discovery and id_token verification"
```

---

### Task 4: SsoOauthProvider adapter

**Files:**

- Create: `apps/api/plane/ee/sso/adapter.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_adapter.py`

**Interfaces:**

- Consumes: `get_sso_config`, `PROVIDERS` (Task 2); `discover`, `verify_id_token` (Task 3); core `OauthAdapter` (`authenticate()`, `get_user_token(data, headers)`, `get_user_response()`, `sanitize_email`, `complete_login_or_signup`).
- Produces: `class SsoOauthProvider(OauthAdapter)`:
  - `__init__(self, request, provider_id, state=None, nonce=None, code_challenge=None, code=None, code_verifier=None, callback=None)` — raises `AuthenticationException(SSO_NOT_CONFIGURED)` if `get_sso_config(provider_id)` is None.
  - `get_auth_url() -> str` (inherited name; URL includes `state`, plus `nonce`, `code_challenge`, `code_challenge_method=S256` when the provider is OIDC-based).
  - `authenticate() -> User` (inherited flow: token exchange → user data → `complete_login_or_signup`).
  - `self.provider == f"sso-{provider_id}"`.
  - `authentication_error_code()` returns `"SSO_PROVIDER_ERROR"`.

Behavior rules:

- OIDC-based (`oidc`, `azure_ad`): issuer = `cfg["ISSUER"].rstrip("/")` or `https://login.microsoftonline.com/{TENANT_ID}/v2.0`; endpoints from `discover(issuer)`; token response must contain `id_token`, verified with `verify_id_token(..., audience=CLIENT_ID, nonce=nonce)`; if `email` claim missing and `userinfo_endpoint` exists, merge `get_user_response()`; Azure fallback `preferred_username`.
- `oauth2`: endpoints from config; claims come from `get_user_response()` (userinfo).
- `email_verified` present and falsy (`False` / `"false"`) → `SSO_PROVIDER_UNVERIFIED_EMAIL`. Absent → accepted.
- `provider_id` (Account) = `claims["sub"]` or `claims["id"]`, as string; missing → `SSO_PROVIDER_ERROR`.
- Names: `given_name`/`family_name`, falling back to splitting `name` on first space.

- [ ] **Step 1: Failing tests** `test_adapter.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.test import RequestFactory

from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import Account, User
from plane.ee.sso.adapter import SsoOauthProvider
from plane.ee.sso.config import config_key, seed_config
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data

ISS = "https://idp.example.com"
META = {
    "issuer": ISS,
    "authorization_endpoint": f"{ISS}/authorize",
    "token_endpoint": f"{ISS}/token",
    "userinfo_endpoint": f"{ISS}/userinfo",
    "jwks_uri": f"{ISS}/jwks",
}


def _configure(provider, **fields):
    seed_config()
    fields = {"ENABLED": "1", "CLIENT_ID": "cid", "CLIENT_SECRET": "sek", **fields}
    for field, value in fields.items():
        row = InstanceConfiguration.objects.get(key=config_key(provider, field))
        row.value = encrypt_data(value) if field == "CLIENT_SECRET" else value
        row.save()


def _request():
    request = RequestFactory().get("/auth/sso/oidc/callback/")
    request.session = {}
    request.META["HTTP_USER_AGENT"] = "pytest"
    return request


@pytest.fixture
def oidc(db, mocker):
    _configure("oidc", ISSUER=ISS)
    mocker.patch("plane.ee.sso.oidc.requests.get").return_value.json.return_value = META


def _token_response(mocker, id_token):
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at", "id_token": id_token}
    return post


@pytest.mark.unit
def test_not_configured_raises(db):
    seed_config()
    with pytest.raises(AuthenticationException) as exc:
        SsoOauthProvider(_request(), "oidc")
    assert exc.value.error_code == 6000


@pytest.mark.unit
def test_auth_url_has_pkce_nonce_state(oidc):
    p = SsoOauthProvider(_request(), "oidc", state="s1", nonce="n1", code_challenge="ch")
    parsed = urlparse(p.get_auth_url())
    q = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == f"{ISS}/authorize"
    assert q["state"] == ["s1"] and q["nonce"] == ["n1"]
    assert q["code_challenge"] == ["ch"] and q["code_challenge_method"] == ["S256"]
    assert q["client_id"] == ["cid"] and q["response_type"] == ["code"]


@pytest.mark.unit
def test_oidc_login_creates_user_and_account(oidc, mocker, make_id_token):
    _token_response(mocker, make_id_token(given_name="An", family_name="Nguyen"))
    p = SsoOauthProvider(_request(), "oidc", code="c", nonce="n1", code_verifier="v")
    user = p.authenticate()
    assert user.email == "a@b.com" and user.first_name == "An" and user.last_name == "Nguyen"
    assert Account.objects.get(user=user).provider == "sso-oidc"
    assert Account.objects.get(user=user).provider_account_id == "u1"


@pytest.mark.unit
def test_oidc_existing_user_is_matched_by_email(oidc, mocker, make_id_token):
    existing = User.objects.create(email="a@b.com", username="x")
    _token_response(mocker, make_id_token())
    user = SsoOauthProvider(_request(), "oidc", code="c", nonce="n1", code_verifier="v").authenticate()
    assert user.id == existing.id


@pytest.mark.unit
@pytest.mark.parametrize("flag", [False, "false"])
def test_unverified_email_rejected(oidc, mocker, make_id_token, flag):
    _token_response(mocker, make_id_token(email_verified=flag))
    with pytest.raises(AuthenticationException) as exc:
        SsoOauthProvider(_request(), "oidc", code="c", nonce="n1", code_verifier="v").authenticate()
    assert exc.value.error_code == 6002


@pytest.mark.unit
def test_missing_id_token_rejected(oidc, mocker):
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    with pytest.raises(AuthenticationException):
        SsoOauthProvider(_request(), "oidc", code="c", nonce="n1", code_verifier="v").authenticate()


@pytest.mark.unit
def test_azure_uses_tenant_issuer_and_preferred_username(db, mocker, make_id_token):
    tenant_iss = "https://login.microsoftonline.com/tid/v2.0"
    _configure("azure_ad", TENANT_ID="tid")
    mocker.patch("plane.ee.sso.oidc.requests.get").return_value.json.return_value = {
        **META,
        "issuer": tenant_iss,
    }
    _token_response(mocker, make_id_token(iss=tenant_iss, email=None, preferred_username="u@corp.com"))
    user = SsoOauthProvider(_request(), "azure_ad", code="c", nonce="n1", code_verifier="v").authenticate()
    assert user.email == "u@corp.com"
    assert Account.objects.get(user=user).provider == "sso-azure_ad"


@pytest.mark.unit
def test_oauth2_generic_uses_userinfo(db, mocker):
    _configure(
        "oauth2",
        AUTH_URL="https://o.example.com/auth",
        TOKEN_URL="https://o.example.com/token",
        USERINFO_URL="https://o.example.com/me",
    )
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    get = mocker.patch("plane.authentication.adapter.oauth.requests.get")
    get.return_value.json.return_value = {"id": 42, "email": "o@x.com", "name": "Bao Tran"}
    user = SsoOauthProvider(_request(), "oauth2", code="c").authenticate()
    assert (user.email, user.first_name, user.last_name) == ("o@x.com", "Bao", "Tran")
    assert Account.objects.get(user=user).provider_account_id == "42"
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.adapter`).

- [ ] **Step 3: Implement** `adapter.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytz

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.adapter.oauth import OauthAdapter
from plane.ee.sso import errors  # noqa: F401
from plane.ee.sso.config import get_sso_config
from plane.ee.sso.oidc import discover, verify_id_token

AZURE_ISSUER = "https://login.microsoftonline.com/{tenant}/v2.0"


def _error(code, message=None):
    return AuthenticationException(
        error_code=AUTHENTICATION_ERROR_CODES[code], error_message=message or code
    )


class SsoOauthProvider(OauthAdapter):
    def __init__(
        self,
        request,
        provider_id,
        state=None,
        nonce=None,
        code_challenge=None,
        code=None,
        code_verifier=None,
        callback=None,
    ):
        cfg = get_sso_config(provider_id)
        if not cfg:
            raise _error("SSO_NOT_CONFIGURED")
        self.provider_id = provider_id
        self.nonce = nonce
        self.code_verifier = code_verifier
        self.issuer = self._issuer(provider_id, cfg)
        if self.issuer:
            meta = discover(self.issuer)
            auth_url = meta.get("authorization_endpoint")
            token_url = meta.get("token_endpoint")
            userinfo_url = meta.get("userinfo_endpoint")
            self.jwks_uri = meta.get("jwks_uri")
            if not (auth_url and token_url and self.jwks_uri):
                raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: incomplete discovery document")
        else:
            auth_url, token_url, userinfo_url = cfg["AUTH_URL"], cfg["TOKEN_URL"], cfg["USERINFO_URL"]

        redirect_uri = (
            f"{'https' if request.is_secure() else 'http'}://{request.get_host()}/auth/sso/{provider_id}/callback/"
        )
        params = {
            "client_id": cfg["CLIENT_ID"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": cfg["SCOPE"],
            "state": state,
        }
        if self.issuer:
            params.update({"nonce": nonce, "code_challenge": code_challenge, "code_challenge_method": "S256"})
        params = {k: v for k, v in params.items() if v}
        super().__init__(
            request,
            f"sso-{provider_id}",
            cfg["CLIENT_ID"],
            cfg["SCOPE"],
            redirect_uri,
            f"{auth_url}?{urlencode(params)}",
            token_url,
            userinfo_url,
            cfg["CLIENT_SECRET"],
            code,
            callback=callback,
        )

    @staticmethod
    def _issuer(provider_id, cfg):
        if provider_id == "oidc":
            return cfg["ISSUER"].rstrip("/")
        if provider_id == "azure_ad":
            return AZURE_ISSUER.format(tenant=cfg["TENANT_ID"].strip())
        return None

    def authentication_error_code(self):
        return "SSO_PROVIDER_ERROR"

    def set_token_data(self):
        data = {
            "code": self.code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        if self.issuer:
            data["code_verifier"] = self.code_verifier
        token = self.get_user_token(data=data, headers={"Accept": "application/json"})
        if not token.get("access_token") and not token.get("id_token"):
            raise _error("SSO_PROVIDER_ERROR")
        self.id_claims = {}
        if self.issuer:
            if not token.get("id_token"):
                raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: id_token missing")
            self.id_claims = verify_id_token(
                token["id_token"], self.jwks_uri, self.issuer, self.client_id, self.nonce
            )
        expires_in = token.get("expires_in")
        super().set_token_data(
            {
                "access_token": token.get("access_token", ""),
                "refresh_token": token.get("refresh_token"),
                "access_token_expired_at": (
                    datetime.now(tz=pytz.utc) + timedelta(seconds=int(expires_in)) if expires_in else None
                ),
                "refresh_token_expired_at": None,
                "id_token": token.get("id_token", ""),
            }
        )

    def set_user_data(self):
        claims = dict(self.id_claims)
        needs_userinfo = not self.issuer or not (claims.get("email") or claims.get("preferred_username"))
        if needs_userinfo and self.userinfo_url and self.token_data.get("access_token"):
            claims = {**self.get_user_response(), **claims}

        verified = claims.get("email_verified")
        if verified is not None and str(verified).lower() != "true":
            raise _error("SSO_PROVIDER_UNVERIFIED_EMAIL")

        email = claims.get("email") or claims.get("preferred_username")
        subject = claims.get("sub") or claims.get("id")
        if not email or subject in (None, ""):
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: missing email or subject")

        first, last = claims.get("given_name"), claims.get("family_name")
        if not (first or last) and claims.get("name"):
            first, _, last = str(claims["name"]).partition(" ")
        super().set_user_data(
            {
                "email": email,
                "user": {
                    "provider_id": str(subject),
                    "first_name": first or "",
                    "last_name": last or "",
                    "avatar": "",
                    "is_password_autoset": True,
                },
            }
        )
```

Note: core `OauthAdapter.set_user_data(self, data)` takes `data`; our override has no param, so the `super().set_user_data(data)` call passes the dict. This mirrors how `GiteaOAuthProvider` is built.

- [ ] **Step 4: Run, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_adapter.py`
If `RequestFactory` requests fail in `save_user_data` (needs `HTTP_USER_AGENT`/IP) the fixture already sets `HTTP_USER_AGENT`; keep `REMOTE_ADDR` default.

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee/sso/adapter.py apps/api/plane/tests/unit/ee/sso/test_adapter.py
git commit -m "feat(ee): SSO OAuth adapter for OIDC, Azure AD and OAuth2"
```

---

### Task 5: Views and URLs

**Files:**

- Create: `apps/api/plane/ee/sso/flow.py`, `apps/api/plane/ee/sso/views.py`, `apps/api/plane/ee/sso/urls.py`
- Modify: `apps/api/plane/ee/urls.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_views.py`

**Interfaces:**

- Consumes: `SsoOauthProvider` (Task 4), `list_enabled_providers` (Task 2).
- Produces `flow.redirect_error(host, exc, next_path=None) -> HttpResponseRedirect`, `flow.provider_error(message="SSO_PROVIDER_ERROR") -> AuthenticationException`, `flow.complete_login(request, user, host, next_path) -> HttpResponseRedirect` (reused by Phase 2/3).
- Produces routes: `GET /auth/sso/providers/` → `200 [{"id","label","protocol"}]`; `GET /auth/sso/<provider_id>/` → 302 to IdP (or to app root with error params); `GET /auth/sso/<provider_id>/callback/` → 302 to app (success path or error params).
- Session keys (popped on callback): `sso_state`, `sso_nonce`, `sso_verifier`.

- [ ] **Step 1: Failing tests** `test_views.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client
from django.utils import timezone

from plane.db.models import User
from plane.ee.sso.config import config_key, seed_config
from plane.license.models import Instance, InstanceConfiguration
from plane.license.utils.encryption import encrypt_data

ISS = "https://idp.example.com"
META = {
    "issuer": ISS,
    "authorization_endpoint": f"{ISS}/authorize",
    "token_endpoint": f"{ISS}/token",
    "jwks_uri": f"{ISS}/jwks",
}


@pytest.fixture
def setup(db, mocker):
    Instance.objects.create(
        instance_name="t",
        instance_id="i",
        current_version="1",
        last_checked_at=timezone.now(),
        is_setup_done=True,
    )
    seed_config()
    for field, value in {
        "ENABLED": "1",
        "LABEL": "ETC SSO",
        "CLIENT_ID": "cid",
        "CLIENT_SECRET": "sek",
        "ISSUER": ISS,
    }.items():
        row = InstanceConfiguration.objects.get(key=config_key("oidc", field))
        row.value = encrypt_data(value) if field == "CLIENT_SECRET" else value
        row.save()
    mocker.patch("plane.ee.sso.oidc.requests.get").return_value.json.return_value = META


def _error_code(response):
    return parse_qs(urlparse(response["Location"]).query).get("error_code", [None])[0]


@pytest.mark.unit
def test_providers_endpoint_lists_enabled(setup):
    response = Client().get("/auth/sso/providers/")
    assert response.status_code == 200
    assert response.json() == [{"id": "oidc", "label": "ETC SSO", "protocol": "oidc"}]


@pytest.mark.unit
def test_initiate_redirects_to_idp_with_pkce(setup):
    response = Client().get("/auth/sso/oidc/")
    assert response.status_code == 302
    location = urlparse(response["Location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{ISS}/authorize"
    q = parse_qs(location.query)
    assert q["code_challenge_method"] == ["S256"] and q["state"] and q["nonce"]


@pytest.mark.unit
def test_initiate_unknown_provider_redirects_with_error(setup):
    response = Client().get("/auth/sso/nope/")
    assert response.status_code == 302 and _error_code(response) == "6000"


@pytest.mark.unit
def test_callback_rejects_state_mismatch(setup):
    client = Client()
    client.get("/auth/sso/oidc/")
    response = client.get("/auth/sso/oidc/callback/?code=c&state=WRONG")
    assert _error_code(response) == "6001"


@pytest.mark.unit
def test_callback_success_logs_user_in(setup, mocker, make_id_token):
    client = Client()
    q = parse_qs(urlparse(client.get("/auth/sso/oidc/")["Location"]).query)
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {
        "access_token": "at",
        "id_token": make_id_token(nonce=q["nonce"][0], email="new@corp.com"),
    }
    response = client.get(f"/auth/sso/oidc/callback/?code=c&state={q['state'][0]}")
    assert response.status_code == 302 and _error_code(response) is None
    assert User.objects.filter(email="new@corp.com").exists()
    # state is single-use
    again = client.get(f"/auth/sso/oidc/callback/?code=c&state={q['state'][0]}")
    assert _error_code(again) == "6001"
```

- [ ] **Step 2: Run, expect FAIL** (404s).

- [ ] **Step 3: Implement**

`flow.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import urlencode, urljoin

from django.http import HttpResponseRedirect

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.login import user_login
from plane.authentication.utils.redirection_path import get_redirection_path
from plane.ee.sso import errors  # noqa: F401
from plane.utils.path_validator import validate_next_path


def redirect_error(host, exc, next_path=None):
    params = exc.get_error_dict()
    if next_path:
        params["next_path"] = str(validate_next_path(next_path))
    return HttpResponseRedirect(urljoin(host, "?" + urlencode(params)))


def provider_error(message="SSO_PROVIDER_ERROR"):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_ERROR"], error_message=message)


def complete_login(request, user, host, next_path):
    """Log the user in and redirect into the app (Phase 3 adds the space target here)."""
    user_login(request=request, user=user, is_app=True)
    path = str(validate_next_path(next_path)) if next_path else get_redirection_path(user=user)
    return HttpResponseRedirect(urljoin(host, path))
```

`views.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import base64
import hashlib
import secrets
import uuid

from django.http import HttpResponseRedirect, JsonResponse
from django.views import View

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.ee.sso.adapter import SsoOauthProvider
from plane.ee.sso.config import list_enabled_providers
from plane.ee.sso.flow import complete_login, provider_error, redirect_error
from plane.license.models import Instance
from plane.utils.path_validator import validate_next_path


class SsoProvidersEndpoint(View):
    def get(self, request):
        return JsonResponse(list_enabled_providers(), safe=False)


class SsoInitiateEndpoint(View):
    def get(self, request, provider_id):
        host = base_host(request=request, is_app=True)
        request.session["host"] = host
        next_path = request.GET.get("next_path")
        if next_path:
            request.session["next_path"] = str(validate_next_path(next_path))

        instance = Instance.objects.first()
        if instance is None or not instance.is_setup_done:
            return redirect_error(
                host,
                AuthenticationException(
                    error_code=AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"],
                    error_message="INSTANCE_NOT_CONFIGURED",
                ),
                next_path,
            )
        try:
            state, nonce = uuid.uuid4().hex, secrets.token_urlsafe(24)
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            provider = SsoOauthProvider(request, provider_id, state=state, nonce=nonce, code_challenge=challenge)
            request.session["sso_state"] = state
            request.session["sso_nonce"] = nonce
            request.session["sso_verifier"] = verifier
            return HttpResponseRedirect(provider.get_auth_url())
        except AuthenticationException as e:
            return redirect_error(host, e, next_path)


class SsoCallbackEndpoint(View):
    def get(self, request, provider_id):
        host = request.session.get("host") or base_host(request=request, is_app=True)
        next_path = request.session.get("next_path")
        # one-time use: pop so a replayed callback fails the state check
        expected_state = request.session.pop("sso_state", None)
        nonce = request.session.pop("sso_nonce", None)
        verifier = request.session.pop("sso_verifier", None)
        code, state = request.GET.get("code"), request.GET.get("state")

        if not code or not expected_state or state != expected_state:
            return redirect_error(host, provider_error(), next_path)
        try:
            provider = SsoOauthProvider(
                request,
                provider_id,
                code=code,
                nonce=nonce,
                code_verifier=verifier,
                callback=post_user_auth_workflow,
            )
            user = provider.authenticate()
            return complete_login(request, user, host, next_path)
        except AuthenticationException as e:
            return redirect_error(host, e, next_path)
```

`sso/urls.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import SsoCallbackEndpoint, SsoInitiateEndpoint, SsoProvidersEndpoint

urlpatterns = [
    path("providers/", SsoProvidersEndpoint.as_view(), name="ee-sso-providers"),
    path("<str:provider_id>/", SsoInitiateEndpoint.as_view(), name="ee-sso-initiate"),
    path("<str:provider_id>/callback/", SsoCallbackEndpoint.as_view(), name="ee-sso-callback"),
]
```

`ee/urls.py`:

```python
from django.urls import include, path

from plane.urls import handler404, urlpatterns as core_urlpatterns  # noqa: F401

urlpatterns = [path("auth/sso/", include("plane.ee.sso.urls")), *core_urlpatterns]
```

(keep the license header at the top).

- [ ] **Step 4: Run all EE tests, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee`
If `test_callback_success_logs_user_in` fails on session cookies set by core's custom `SessionMiddleware`, inspect `plane/authentication/middleware/session.py` for the host-dependent cookie name and set the test client's `HTTP_HOST` accordingly (e.g. `Client(HTTP_HOST="localhost")`); do not weaken the production code.

- [ ] **Step 5: Confirm core suite still passes unchanged** (the plugin must not change core behavior)

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m unit`
Expected: same pass count as before the branch.

- [ ] **Step 6: Commit**

```bash
git add apps/api/plane/ee apps/api/plane/tests/unit/ee
git commit -m "feat(ee): SSO initiate/callback/providers endpoints"
```

---

## Self-Review (done against the spec)

- Spec coverage for Phase 1: plugin activation (T1), config in InstanceConfiguration (T2), OIDC with PKCE + JWKS + nonce + iss/aud/exp (T3, T4, T5), Azure AD preset (T4), generic OAuth2 (T4), `/auth/sso/providers/` + initiate/callback (T5), verified-email rule, JIT signup via core `ENABLE_SIGNUP` (inherited from `complete_login_or_signup`), error codes 6xxx (T1). SAML, frontend, admin UI, Docker are deferred to later plans as stated.
- Known limits to carry forward: Azure is single-tenant only (no `common`/`organizations` issuer templating); sync of profile data on later logins is off (`check_sync_enabled` has no `sso-*` key); discovery cached 1h.
- Type/name consistency checked: `get_sso_config`, `config_key`, `seed_config`, `list_enabled_providers`, `SsoOauthProvider` kwargs (`state`, `nonce`, `code_challenge`, `code`, `code_verifier`, `callback`), session keys `sso_state/sso_nonce/sso_verifier` are identical across tasks.
- Not verified by running: this plan was written against code reading only; Task 5's session-cookie behavior is the most likely place to need an adjustment (noted in Step 4).
