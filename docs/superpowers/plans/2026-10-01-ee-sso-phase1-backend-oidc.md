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
- Ruff selects `E501` (120 columns, also for tests): wrap long lines and run `ruff check` before committing.
- Identity is the stable subject, never an e-mail: OIDC `(iss, sub)`, Entra `tid:oid`, SAML persistent NameID, OAuth2 userinfo id. E-mail claims, `email_verified`, `preferred_username` and UPN are never read as identity and users are never matched or linked by e-mail automatically (existing users are linked by an admin with `sso_link`). JIT users get a `<hash>@sso.invalid` placeholder e-mail.
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
apps/api/plane/ee/sso/identity.py             # subject-keyed login (SubjectLoginMixin), placeholder e-mail
apps/api/plane/ee/management/commands/sso_link.py  # admin: link existing Plane users to an SSO subject
apps/api/plane/ee/sso/views.py                # providers list, initiate, callback
apps/api/plane/ee/sso/urls.py
apps/api/plane/tests/unit/ee/__init__.py
apps/api/plane/tests/unit/ee/sso/__init__.py
apps/api/plane/tests/unit/ee/conftest.py      # skips EE tests unless plane.ee is installed
apps/api/plane/tests/unit/ee/sso/conftest.py  # RSA key + id_token helper
apps/api/plane/tests/unit/ee/sso/test_*.py
```

---

### Task 1: Plugin skeleton and settings

**Files:**

- Create: `apps/api/plane/settings/ee.py`, `apps/api/plane/settings/ee_test.py`
- Create: `apps/api/plane/ee/__init__.py`, `apps/api/plane/ee/apps.py`, `apps/api/plane/ee/urls.py`
- Create: `apps/api/plane/ee/sso/__init__.py`, `apps/api/plane/ee/sso/errors.py`
- Create: `apps/api/plane/tests/unit/ee/__init__.py`, `apps/api/plane/tests/unit/ee/sso/__init__.py`, `apps/api/plane/tests/unit/ee/conftest.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_skeleton.py`

**Interfaces:**

- Produces: `plane.ee.sso.errors.EE_SSO_ERROR_CODES` (dict) registered into `AUTHENTICATION_ERROR_CODES` with keys `SSO_NOT_CONFIGURED=6000`, `SSO_PROVIDER_ERROR=6001`.
- Produces: `plane.ee.apps.EeConfig` (label `ee`); `plane.ee.urls.urlpatterns` and `handler404`.
- Produces: settings modules `plane.settings.ee`, `plane.settings.ee_test`.

- [ ] **Step 1: Create empty package files** (`ee/__init__.py`, `ee/sso/__init__.py`, `tests/unit/ee/__init__.py`, `tests/unit/ee/sso/__init__.py`) containing only the license header, plus `tests/unit/ee/conftest.py`. The default suite (`pytest.ini`, compose default command, `pytest -m unit`) runs under `plane.settings.test` where `plane.ee` is not installed, so EE tests must be skipped there instead of failing:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings

# EE tests only make sense under plane.settings.ee_test (--ds). Otherwise do not collect them.
collect_ignore_glob = [] if "plane.ee" in settings.INSTALLED_APPS else ["sso/*", "test_*.py"]
```

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
    assert cfg["SCOPE"] == "openid profile"
    assert list_enabled_providers() == [{"id": "oidc", "label": "ETC SSO", "protocol": "oidc"}]


@pytest.mark.unit
@pytest.mark.django_db
def test_azure_requires_a_guid_tenant():
    seed_config()
    for f, v in [("ENABLED", "1"), ("CLIENT_ID", "c"), ("TENANT_ID", "contoso.onmicrosoft.com")]:
        _set("azure_ad", f, v)
    _set("azure_ad", "CLIENT_SECRET", "s", encrypted=True)
    assert get_sso_config("azure_ad") is None
    for bad in ("common", "organizations", "consumers"):
        _set("azure_ad", "TENANT_ID", bad)
        assert get_sso_config("azure_ad") is None
    _set("azure_ad", "TENANT_ID", "11111111-1111-1111-1111-111111111111")
    assert get_sso_config("azure_ad") is not None


@pytest.mark.unit
@pytest.mark.django_db
def test_allow_signup_defaults_to_on_and_enabled_to_off():
    seed_config()
    assert InstanceConfiguration.objects.get(key="EE_SSO_AZURE_AD_ALLOW_SIGNUP").value == "1"
    assert InstanceConfiguration.objects.get(key="EE_SSO_AZURE_AD_ENABLED").value == "0"


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_invalidates_cached_configuration_list():
    from django.core.cache import cache

    # the test DB already holds seeded rows (post_migrate), so start from an empty table
    InstanceConfiguration.objects.filter(key__startswith="EE_SSO_").delete()
    cache.set("/api/instances/configurations/", ["stale"])
    seed_config()
    assert cache.get("/api/instances/configurations/") is None


@pytest.mark.unit
def test_callback_url_default_and_override(settings):
    from django.test import RequestFactory

    from plane.ee.sso.config import callback_url

    settings.WEB_URL = "https://plane.example.com/"
    request = RequestFactory().get("/")
    assert callback_url(request, "oidc", {}) == "https://plane.example.com/auth/sso/oidc/callback/"
    assert callback_url(request, "saml", {}) == "https://plane.example.com/auth/sso/saml/acs/"
    assert callback_url(request, "oidc", {"CALLBACK_URL": " https://sso.corp.com/cb/ "}) == "https://sso.corp.com/cb/"
    # non-absolute values are ignored
    assert callback_url(request, "oidc", {"CALLBACK_URL": "/relative"}) == "https://plane.example.com/auth/sso/oidc/callback/"


@pytest.mark.unit
@pytest.mark.django_db
def test_default_label_when_blank():
    seed_config()
    for f, v in [("ENABLED", "1"), ("CLIENT_ID", "c"), ("TENANT_ID", "11111111-1111-1111-1111-111111111111")]:
        _set("azure_ad", f, v)
    _set("azure_ad", "CLIENT_SECRET", "s", encrypted=True)
    assert list_enabled_providers()[0]["label"] == "Microsoft"
```

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.config`).

- [ ] **Step 3: Implement** `config.py`.

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

from django.conf import settings
from django.core.cache import cache

from plane.license.models import InstanceConfiguration
from plane.license.utils.instance_value import get_configuration_value

DEFAULT_SCOPE = "openid profile"  # least privilege: e-mail is never used
GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OAUTH_FIELDS = ["CLIENT_ID", "CLIENT_SECRET", "SCOPE"]
ENCRYPTED_FIELDS = {"CLIENT_SECRET"}

# Every provider also has ENABLED and LABEL (see BASE_FIELDS). `fields` are the provider-specific
# extras; `required` must all be non-empty for the provider to count as configured. Phase 2 adds "saml".
PROVIDERS = {
    "oidc": {
        "label": "OpenID Connect",
        "protocol": "oidc",
        "fields": [*OAUTH_FIELDS, "ISSUER", "CALLBACK_URL", "ALLOW_SIGNUP"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "ISSUER"],
    },
    "azure_ad": {
        "label": "Microsoft",
        "protocol": "oidc",
        "fields": [*OAUTH_FIELDS, "TENANT_ID", "ISSUER", "CALLBACK_URL", "ALLOW_SIGNUP"],  # ISSUER optional override
        "required": ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"],
    },
    "oauth2": {
        "label": "OAuth2",
        "protocol": "oauth2",
        "fields": [*OAUTH_FIELDS, "AUTH_URL", "TOKEN_URL", "USERINFO_URL", "CALLBACK_URL", "ALLOW_SIGNUP"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "AUTH_URL", "TOKEN_URL", "USERINFO_URL"],
    },
}
PROVIDER_IDS = tuple(PROVIDERS)
BASE_FIELDS = ["ENABLED", "LABEL"]
# seeded defaults; ALLOW_SIGNUP is the per-provider "allow sign-up" option ("0": only existing users may log in here)
DEFAULT_VALUES = {"ENABLED": "0", "ALLOW_SIGNUP": "1"}


def config_key(provider_id, field):
    return f"EE_SSO_{provider_id.upper()}_{field}"


def _fields(provider_id):
    return BASE_FIELDS + PROVIDERS[provider_id]["fields"]


def seed_config(**_kwargs):
    created_any = False
    for provider_id in PROVIDER_IDS:
        for field in _fields(provider_id):
            _, created = InstanceConfiguration.objects.get_or_create(
                key=config_key(provider_id, field),
                defaults={
                    "value": DEFAULT_VALUES.get(field, ""),
                    "category": f"EE_SSO_{provider_id.upper()}",
                    "is_encrypted": field in ENCRYPTED_FIELDS,
                },
            )
            created_any = created_any or created
    if created_any:
        # core caches GET /api/instances/configurations/ for 2h and only PATCH invalidates it; without this
        # the admin UI would not see freshly seeded keys on an existing instance.
        cache.delete_many(["/api/instances/configurations/", "/api/instances/"])


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
    # Azure AD is single-tenant: TENANT_ID must be the tenant GUID (not a domain, `common`, `organizations`,
    # `consumers`). Azure publishes the GUID in the discovery issuer / `tid` claim, so anything else can never match.
    if provider_id == "azure_ad" and not GUID_RE.fullmatch(cfg["TENANT_ID"].strip().lower()):
        return None
    if "SCOPE" in cfg:
        cfg["SCOPE"] = cfg["SCOPE"] or DEFAULT_SCOPE
    if "ALLOW_SIGNUP" in cfg:
        cfg["ALLOW_SIGNUP"] = cfg["ALLOW_SIGNUP"] or "1"
    cfg["LABEL"] = cfg["LABEL"] or PROVIDERS[provider_id]["label"]
    return cfg


def public_origin(request):
    """Public base URL of this Plane instance. Prefers the configured WEB_URL/APP_BASE_URL (not Host-header
    controlled); falls back to the request only when neither is set."""
    configured = settings.WEB_URL or settings.APP_BASE_URL
    if configured:
        return configured.rstrip("/")
    return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"


def callback_url(request, provider_id, cfg):
    """Redirect URI (OIDC/Azure/OAuth2) or ACS URL (SAML) sent to / registered at the IdP.
    An admin-set CALLBACK_URL wins; it must be absolute http(s) and must still reach our endpoint."""
    custom = (cfg.get("CALLBACK_URL") or "").strip()
    if custom.startswith(("http://", "https://")):
        return custom
    path = "acs" if provider_id == "saml" else "callback"
    return f"{public_origin(request)}/auth/sso/{provider_id}/{path}/"


def list_enabled_providers():
    out = []
    for provider_id in PROVIDER_IDS:
        cfg = get_sso_config(provider_id)
        if cfg:
            out.append({"id": provider_id, "label": cfg["LABEL"], "protocol": PROVIDERS[provider_id]["protocol"]})
    return out
```

Replace `plane/ee/apps.py` with its final form (seeding hooks `post_migrate` of the `license` app, because `plane.ee` has no models and Django emits `post_migrate` only for apps with models):

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_on_license_migrate(sender, **kwargs):
    if sender.label == "license":  # LicenseConfig has no explicit label, so it is "license"
        from plane.ee.sso.config import seed_config

        seed_config()


class EeConfig(AppConfig):
    name = "plane.ee"
    label = "ee"

    def ready(self):
        from plane.ee.sso import errors  # noqa: F401  (registers error codes)

        post_migrate.connect(_seed_on_license_migrate, dispatch_uid="ee_sso_seed")
```

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
    # delete only our keys (cache.clear() would flush the whole shared Redis DB); needs the compose Redis
    cache.delete_pattern("ee_sso_*")
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
        ({"aud": ["cid", "other"], "azp": "other"}, {}),  # multi-audience token for another authorized party
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
    fetch = mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={"issuer": ISS, "jwks_uri": f"{ISS}/jwks"})
    assert discover(ISS)["jwks_uri"] == f"{ISS}/jwks"
    discover(ISS)
    assert fetch.call_count == 1


@pytest.mark.unit
def test_discover_accepts_trailing_slash_issuer(mocker, make_id_token):
    fetch = mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={"issuer": ISS + "/", "jwks_uri": "x"})
    meta = discover(ISS)  # configured without slash
    assert fetch.call_args.args[0] == f"{ISS}/.well-known/openid-configuration"
    # tokens are then verified against the verbatim issuer
    assert _verify(make_id_token(iss=ISS + "/"), issuer=meta["issuer"])["sub"] == "u1"


@pytest.mark.unit
def test_discover_issuer_mismatch_rejected(mocker):
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={"issuer": "https://other", "jwks_uri": "x"})
    with pytest.raises(AuthenticationException):
        discover(ISS)
```

- [ ] **Step 3: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.oidc`).

- [ ] **Step 4: Implement** `oidc.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import lru_cache

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


def _fetch_json(url):
    # Single patch point for tests (patching requests.get itself would also mock the core adapter's calls).
    # ponytail: admin-configured URL, not SSRF-guarded (internal IdPs are legitimate); see Known limits.
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def discover(issuer):
    base = issuer.rstrip("/")
    cache_key = f"ee_sso_discovery:{base}"
    meta = cache.get(cache_key)
    if meta:
        return meta
    try:
        meta = _fetch_json(f"{base}/.well-known/openid-configuration")
    except (requests.RequestException, ValueError):
        raise _provider_error("discovery failed")
    # OIDC Discovery §4.3: issuer in metadata must match the one used to fetch it. Some IdPs (Auth0) publish
    # it with a trailing slash, so compare ignoring that one character; callers must then verify tokens
    # against meta["issuer"] verbatim.
    if str(meta.get("issuer", "")).rstrip("/") != base:
        raise _provider_error("issuer mismatch")
    cache.set(cache_key, meta, DISCOVERY_TTL)
    return meta


@lru_cache(maxsize=16)
def _jwk_client(jwks_uri):
    return jwt.PyJWKClient(jwks_uri, timeout=10)  # keeps its own key cache


def _signing_key(jwks_uri, id_token):
    return _jwk_client(jwks_uri).get_signing_key_from_jwt(id_token).key


def verify_id_token(id_token, jwks_uri, issuer, audience, nonce):
    try:
        claims = jwt.decode(
            id_token,
            _signing_key(jwks_uri, id_token),
            algorithms=ALLOWED_ALGS,
            audience=audience,
            issuer=issuer,
            leeway=60,  # clock skew
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError:
        raise _provider_error("invalid id_token")
    if not nonce or claims.get("nonce") != nonce:
        raise _provider_error("nonce mismatch")
    # OIDC Core 3.1.3.7: with several audiences the authorized party (azp) must be this client
    if isinstance(claims.get("aud"), list) and len(claims["aud"]) > 1 and claims.get("azp") != audience:
        raise _provider_error("azp mismatch")
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

### Task 4: Subject-keyed login (`identity.py`) and `SsoOauthProvider`

**Decision: identity is the stable subject, never an e-mail.** None of the identity providers send a usable e-mail, and best practice says not to use one anyway: OIDC Core (§2, §5.7) — `sub` is the only identifier that is stable and never reassigned, and is unique only _per issuer_, so the key is `(iss, sub)`; Microsoft Entra — use `oid` together with `tid` (`sub` is per-application, and `preferred_username`, UPN and `email` are mutable and must not identify or authorize a user); SAML Core §8.3.7 — a `persistent` NameID is the stable pairwise identifier (e-mail / unspecified NameIDs are reassignable); OAuth 2.0 Security BCP and RFC 9700 — do not link accounts by unverified e-mail (account-pre-hijacking). Therefore e-mail claims, `email_verified`, `preferred_username` and UPN are **never** read as identity, and Plane users are never matched or linked by e-mail automatically.

Plane requires a unique e-mail per user, so a user created at first login gets a reserved-domain placeholder `<hash>@sso.invalid` (RFC 2606: it can never be a real mailbox, so a pending workspace invite addressed to a real e-mail can never auto-attach to an SSO user, and an SSO user can never collide with a real account). Existing Plane users are linked **explicitly by an administrator** with the `sso_link` command (Task 6). Consequence: Plane's e-mail notifications and e-mail invites do not reach SSO-created users (documented limit).

**Files:**

- Create: `apps/api/plane/ee/sso/flow.py` (code under Task 5 Step 3; created here because `identity.py` imports `provider_error` from it), `apps/api/plane/ee/sso/identity.py`, `apps/api/plane/ee/sso/adapter.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_identity.py`, `apps/api/plane/tests/unit/ee/sso/test_adapter.py`

**Interfaces:**

- Consumes: `get_sso_config`, `PROVIDERS`, `callback_url` (Task 2); `discover`, `verify_id_token` (Task 3); core `OauthAdapter` (`get_user_token`, `get_user_response`), core `Adapter` (`save_user_data`, `callback`, `request`, `provider`).
- Produces (`identity.py`):
  - `issuer_fingerprint(issuer: str) -> str` (first 12 hex of sha256).
  - `subject_key(issuer: str, subject) -> str` = `"<fingerprint>:<subject>"`; raises `AuthenticationException(SSO_PROVIDER_ERROR)` when the subject is empty or the key exceeds 255 chars (`Account.provider_account_id`).
  - `placeholder_email(provider: str, key: str) -> str` = `"<32 hex>@sso.invalid"`, deterministic.
  - `class SubjectLoginMixin` with `login_by_subject(self, key: str, profile: dict, allow_signup: str) -> User`. `profile` keys: `first_name`, `last_name`, `display_name`. Finds the user through `Account(provider=self.provider, provider_account_id=key)`; otherwise provisions one (blocked by `allow_signup != "1"` or the instance-wide `ENABLE_SIGNUP == "0"` with `SIGNUP_DISABLED` 5015); rejects deactivated users (5019) and bots (5017); updates `last_connected_at`; calls `save_user_data` and `self.callback(user, is_signup, request)`. No access/refresh tokens are persisted (least privilege).
- Produces (`adapter.py`): `SsoOauthProvider(request, provider_id, state=None, nonce=None, code_challenge=None, code=None, code_verifier=None, callback=None)`; `get_auth_url()`; `authenticate() -> User`; `provider == f"sso-{provider_id}"`.

Subject rules per provider:

- **oidc:** key = `subject_key(<discovery issuer, verbatim>, id_token.sub)`. Profile from `given_name` / `family_name` (else `name` split), display name from `name` or `preferred_username` (display only).
- **azure_ad (single tenant):** `tid` must equal the configured Tenant ID (always; `get_sso_config` guarantees it is a GUID); `oid` is required; key = `"<tid>:<oid>"`; B2B guests rejected (`idp` present and different from `iss`, `acct == 1`, or `#EXT#` in a present `preferred_username`). No userinfo/Graph call. For authorization use Entra's **"Assignment required"** on the enterprise application (assign users/groups there); that is the authoritative access control and replaces group sync.
- **oauth2 (generic):** key = `subject_key(<token URL>, userinfo.sub or userinfo.id)`; profile from userinfo `given_name`/`family_name`/`name`. (Plain OAuth2 is not an authentication protocol; prefer OIDC where the IdP offers it.)

- [ ] **Step 1: Failing tests** `test_identity.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.test import RequestFactory
from django.utils import timezone

from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import Account, Profile
from plane.ee.sso.identity import SubjectLoginMixin, placeholder_email, subject_key
from plane.license.models import InstanceConfiguration


class _Provider(SubjectLoginMixin, Adapter):
    pass


def _provider(callback=None):
    request = RequestFactory().get("/")
    request.META["HTTP_USER_AGENT"] = "pytest"
    return _Provider(request, "sso-test", callback)


PROFILE = {"first_name": "An", "last_name": "Nguyen", "display_name": "An Nguyen"}
KEY = subject_key("https://idp.example.com", "sub-1")


@pytest.mark.unit
def test_subject_key_is_namespaced_by_issuer():
    assert subject_key("https://a", "1") != subject_key("https://b", "1")
    assert subject_key("https://a", "1") == subject_key("https://a", "1")
    assert subject_key("https://a/", "1") == subject_key("https://a", "1")


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["", None, "x" * 300])
def test_subject_key_rejects_empty_or_oversized(subject):
    with pytest.raises(AuthenticationException):
        subject_key("https://a", subject)


@pytest.mark.unit
def test_placeholder_email_is_reserved_and_deterministic():
    email = placeholder_email("sso-test", KEY)
    assert email.endswith("@sso.invalid")
    assert email == placeholder_email("sso-test", KEY)


@pytest.mark.unit
@pytest.mark.django_db
def test_first_login_provisions_user_account_profile_and_runs_workflow(mocker):
    callback = mocker.Mock()
    user = _provider(callback).login_by_subject(KEY, PROFILE, "1")
    assert user.email == placeholder_email("sso-test", KEY)
    assert (user.first_name, user.last_name) == ("An", "Nguyen")
    assert Account.objects.get(user=user).provider_account_id == KEY
    assert Profile.objects.filter(user=user).exists()
    assert not user.has_usable_password() or user.is_password_autoset
    assert callback.call_args.args[1] is True  # is_signup


@pytest.mark.unit
@pytest.mark.django_db
def test_second_login_reuses_the_user_even_with_signup_off(mocker):
    first = _provider().login_by_subject(KEY, PROFILE, "1")
    callback = mocker.Mock()
    second = _provider(callback).login_by_subject(KEY, {}, "0")
    assert second.id == first.id
    assert Account.objects.count() == 1
    assert callback.call_args.args[1] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_signup_off_blocks_unknown_subjects():
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "0")
    assert exc.value.error_code == 5015
    assert Account.objects.count() == 0


@pytest.mark.unit
@pytest.mark.django_db
def test_instance_wide_signup_off_blocks_unknown_subjects():
    InstanceConfiguration.objects.create(key="ENABLE_SIGNUP", value="0", category="AUTHENTICATION")
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "1")
    assert exc.value.error_code == 5015


@pytest.mark.unit
@pytest.mark.django_db
def test_login_after_the_link_was_removed_reuses_the_placeholder_user():
    first = _provider().login_by_subject(KEY, PROFILE, "1")
    Account.objects.all().delete()  # e.g. `sso_link --unlink`
    assert _provider().login_by_subject(KEY, PROFILE, "1").id == first.id
    assert Account.objects.count() == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_deactivated_and_bot_users_are_rejected():
    user = _provider().login_by_subject(KEY, PROFILE, "1")
    user.is_active, user.last_logout_time = False, timezone.now()
    user.save()
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "1")
    assert exc.value.error_code == 5019
    user.is_active, user.last_logout_time, user.is_bot = True, None, True
    user.save()
    with pytest.raises(AuthenticationException) as exc:
        _provider().login_by_subject(KEY, PROFILE, "1")
    assert exc.value.error_code == 5017
```

`test_adapter.py`:

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
from plane.ee.sso.config import PROVIDERS, config_key, seed_config
from plane.ee.sso.identity import issuer_fingerprint, placeholder_email, subject_key
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
GUID = "11111111-1111-1111-1111-111111111111"
OTHER_GUID = "22222222-2222-2222-2222-222222222222"


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


def _token_response(mocker, id_token):
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at", "id_token": id_token}
    return post


def _auth(provider_id):
    return SsoOauthProvider(_request(), provider_id, code="c", nonce="n1", code_verifier="v").authenticate()


@pytest.fixture
def oidc(db, mocker):
    _configure("oidc", ISSUER=ISS)
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)


def _azure(mocker, **cfg):
    iss = cfg.pop("iss", f"https://login.microsoftonline.com/{GUID}/v2.0")
    _configure("azure_ad", TENANT_ID=GUID, **cfg)
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={**META, "issuer": iss})
    return iss


@pytest.mark.unit
def test_not_configured_raises(db):
    seed_config()
    with pytest.raises(AuthenticationException) as exc:
        SsoOauthProvider(_request(), "oidc")
    assert exc.value.error_code == 6000


@pytest.mark.unit
def test_auth_url_has_pkce_nonce_state_and_no_email_scope(oidc):
    p = SsoOauthProvider(_request(), "oidc", state="s1", nonce="n1", code_challenge="ch")
    q = parse_qs(urlparse(p.get_auth_url()).query)
    assert q["state"] == ["s1"] and q["nonce"] == ["n1"]
    assert q["code_challenge"] == ["ch"] and q["code_challenge_method"] == ["S256"]
    assert q["client_id"] == ["cid"] and q["response_type"] == ["code"]
    assert q["scope"] == ["openid profile"]  # least privilege: we never ask for e-mail


@pytest.mark.unit
def test_custom_callback_url_is_used_everywhere(db, mocker, make_id_token):
    _configure("oidc", ISSUER=ISS, CALLBACK_URL="https://sso.corp.com/auth/sso/oidc/callback/")
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)
    p = SsoOauthProvider(_request(), "oidc", state="s1", nonce="n1", code_challenge="ch")
    assert parse_qs(urlparse(p.get_auth_url()).query)["redirect_uri"] == ["https://sso.corp.com/auth/sso/oidc/callback/"]
    post = _token_response(mocker, make_id_token())
    _auth("oidc")
    assert post.call_args.kwargs["data"]["redirect_uri"] == "https://sso.corp.com/auth/sso/oidc/callback/"


@pytest.mark.unit
def test_saml_provider_id_is_rejected_by_oauth_adapter(db):
    if "saml" not in PROVIDERS:
        pytest.skip("saml added in phase 2")
    with pytest.raises(AuthenticationException) as exc:
        SsoOauthProvider(_request(), "saml")
    assert exc.value.error_code == 6000


@pytest.mark.unit
def test_oidc_identity_is_issuer_plus_sub_and_email_claims_are_ignored(oidc, mocker, make_id_token):
    _token_response(mocker, make_id_token(name="An Nguyen", email="a@b.com", email_verified=False))
    user = _auth("oidc")
    key = f"{issuer_fingerprint(ISS)}:u1"
    assert Account.objects.get(user=user).provider_account_id == key
    assert Account.objects.get(user=user).provider == "sso-oidc"
    assert user.email == placeholder_email("sso-oidc", key)
    assert (user.first_name, user.last_name) == ("An", "Nguyen")
    assert not User.objects.filter(email="a@b.com").exists()


@pytest.mark.unit
def test_existing_plane_user_with_the_same_email_is_never_taken_over(oidc, mocker, make_id_token):
    victim = User.objects.create(email="a@b.com", username="victim")
    _token_response(mocker, make_id_token(email="a@b.com", email_verified=True))
    user = _auth("oidc")
    assert user.id != victim.id
    assert not Account.objects.filter(user=victim).exists()


@pytest.mark.unit
def test_same_subject_logs_into_the_same_user_and_other_subject_does_not(oidc, mocker, make_id_token):
    _token_response(mocker, make_id_token(sub="s1"))
    first = _auth("oidc")
    _token_response(mocker, make_id_token(sub="s1", email="changed@b.com"))
    assert _auth("oidc").id == first.id
    _token_response(mocker, make_id_token(sub="s2"))
    assert _auth("oidc").id != first.id


@pytest.mark.unit
def test_missing_id_token_rejected(oidc, mocker):
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    with pytest.raises(AuthenticationException):
        _auth("oidc")


@pytest.mark.unit
def test_azure_identity_is_tid_plus_oid_and_never_calls_userinfo(db, mocker, make_id_token):
    iss = _azure(mocker)
    get = mocker.patch("plane.authentication.adapter.oauth.requests.get")
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="OID-1", preferred_username="an@corp.com", name="An Nguyen"))
    user = _auth("azure_ad")
    assert Account.objects.get(user=user).provider == "sso-azure_ad"
    assert Account.objects.get(user=user).provider_account_id == f"{GUID}:oid-1"
    assert user.email.endswith("@sso.invalid")  # UPN is display data only, never the e-mail
    get.assert_not_called()


@pytest.mark.unit
def test_azure_upn_change_does_not_change_the_account(db, mocker, make_id_token):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="o1", preferred_username="old@corp.com"))
    first = _auth("azure_ad")
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="o1", preferred_username="renamed@corp.com"))
    assert _auth("azure_ad").id == first.id


@pytest.mark.unit
def test_azure_reassigned_upn_with_a_new_oid_is_a_different_user(db, mocker, make_id_token):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="leaver", preferred_username="an@corp.com"))
    leaver = _auth("azure_ad")
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="newhire", preferred_username="an@corp.com"))
    assert _auth("azure_ad").id != leaver.id


@pytest.mark.unit
@pytest.mark.parametrize("claims", [{"tid": OTHER_GUID, "oid": "o"}, {"tid": GUID}, {"oid": "o"}])
def test_azure_requires_matching_tid_and_an_oid(db, mocker, make_id_token, claims):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, **claims))
    with pytest.raises(AuthenticationException) as exc:
        _auth("azure_ad")
    assert exc.value.error_code == 6001


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"acct": 1},
        {"idp": "https://sts.example.com/"},
        {"preferred_username": "bob_partner.com#EXT#@corp.onmicrosoft.com"},
    ],
)
def test_azure_guest_signals_are_rejected(db, mocker, make_id_token, extra):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="o", **extra))
    with pytest.raises(AuthenticationException) as exc:
        _auth("azure_ad")
    assert exc.value.error_code == 6001


@pytest.mark.unit
def test_azure_uppercase_tenant_guid_is_normalised_for_discovery(db, mocker):
    _configure("azure_ad", TENANT_ID=GUID.upper())
    lower_iss = f"https://login.microsoftonline.com/{GUID}/v2.0"
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={**META, "issuer": lower_iss})
    assert SsoOauthProvider(_request(), "azure_ad", state="s", nonce="n", code_challenge="c").issuer == lower_iss


@pytest.mark.unit
def test_azure_issuer_override_is_used_for_discovery(db, mocker):
    override = "https://login.microsoftonline.com/custom/v2.0"
    iss = _azure(mocker, ISSUER=override, iss=override)
    p = SsoOauthProvider(_request(), "azure_ad", state="s", nonce="n", code_challenge="c")
    assert p.issuer == iss and p.token_issuer == iss


@pytest.mark.unit
def test_oauth2_identity_is_the_userinfo_id(db, mocker):
    _configure(
        "oauth2",
        AUTH_URL="https://o.example.com/auth",
        TOKEN_URL="https://o.example.com/token",
        USERINFO_URL="https://o.example.com/me",
    )
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    get = mocker.patch("plane.authentication.adapter.oauth.requests.get")
    get.return_value.json.return_value = {"id": 42, "name": "Bao Tran"}
    user = SsoOauthProvider(_request(), "oauth2", code="c").authenticate()
    assert (user.first_name, user.last_name) == ("Bao", "Tran")
    assert Account.objects.get(user=user).provider_account_id == subject_key("https://o.example.com/token", "42")


@pytest.mark.unit
def test_oauth2_without_a_stable_id_is_rejected(db, mocker):
    _configure(
        "oauth2",
        AUTH_URL="https://o.example.com/auth",
        TOKEN_URL="https://o.example.com/token",
        USERINFO_URL="https://o.example.com/me",
    )
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    mocker.patch("plane.authentication.adapter.oauth.requests.get").return_value.json.return_value = {"name": "x"}
    with pytest.raises(AuthenticationException):
        SsoOauthProvider(_request(), "oauth2", code="c").authenticate()
```

(The `make_id_token` fixture in `conftest.py` still emits an `email` claim by default: that is deliberate, it proves the claim is ignored.)

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.identity`).

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_identity.py plane/tests/unit/ee/sso/test_adapter.py`

- [ ] **Step 3: Implement.** First create `flow.py` exactly as in Task 5 Step 3 (it is needed here). Then `identity.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import hashlib
import os
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.db.models import Account, Profile, User
from plane.ee.sso.flow import provider_error
from plane.license.utils.instance_value import get_configuration_value

# RFC 2606 reserved TLD: can never be a real mailbox (see the Task 4 decision text).
PLACEHOLDER_DOMAIN = "sso.invalid"


def issuer_fingerprint(issuer):
    # a trailing "/" is not significant (Auth0 publishes it, admins often omit it)
    return hashlib.sha256(issuer.rstrip("/").encode()).hexdigest()[:12]


def subject_key(issuer, subject):
    """`sub` is only unique per issuer (OIDC Core 2): namespace it. Never built from an e-mail."""
    subject = "" if subject is None else str(subject)
    key = f"{issuer_fingerprint(issuer)}:{subject}"
    if not subject or len(key) > 255:  # Account.provider_account_id is 255 chars
        raise provider_error("SSO_PROVIDER_ERROR: missing or oversized subject")
    return key


def placeholder_email(provider, key):
    return f"{hashlib.sha256(f'{provider}|{key}'.encode()).hexdigest()[:32]}@{PLACEHOLDER_DOMAIN}"


def _clip(value):
    return str(value or "").strip()[:255]


def _reject(code):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[code], error_message=code)


class SubjectLoginMixin:
    """For core `Adapter` subclasses: log in through (provider, stable subject), never through e-mail."""

    def login_by_subject(self, key, profile, allow_signup):
        account = Account.objects.select_related("user").filter(provider=self.provider, provider_account_id=key).first()
        is_signup = account is None
        if account is not None:
            user = account.user
        else:
            self._check_signup(allow_signup)
            try:
                with transaction.atomic():
                    user = self._provision(key, profile)
                    Account.objects.create(user=user, provider=self.provider, provider_account_id=key, access_token="")
            except IntegrityError:
                # concurrent first login for the same subject (the other request won), or a placeholder user whose
                # link was removed (`sso_link --unlink`): re-use that user and (re)create the link
                account = Account.objects.select_related("user").filter(provider=self.provider, provider_account_id=key).first()
                user = account.user if account else User.objects.get(email=placeholder_email(self.provider, key))
                if account is None:
                    Account.objects.get_or_create(
                        provider=self.provider, provider_account_id=key, defaults={"user": user, "access_token": ""}
                    )
                is_signup = False
        if not user.is_active and user.last_logout_time is not None:
            raise _reject("USER_ACCOUNT_DEACTIVATED")  # explicitly deactivated (same rule as core)
        if user.is_bot:
            raise _reject("BOT_USER_LOGIN_FORBIDDEN")
        Account.objects.filter(provider=self.provider, provider_account_id=key).update(last_connected_at=timezone.now())
        user = self.save_user_data(user)
        if self.callback:
            self.callback(user, is_signup, self.request)
        return user

    def _check_signup(self, allow_signup):
        (enable_signup,) = get_configuration_value(
            [{"key": "ENABLE_SIGNUP", "default": os.environ.get("ENABLE_SIGNUP", "1")}]
        )
        if allow_signup != "1" or enable_signup == "0":
            raise _reject("SIGNUP_DISABLED")

    def _provision(self, key, profile):
        email = placeholder_email(self.provider, key)
        user = User(
            email=email,
            username=uuid.uuid4().hex,
            first_name=_clip(profile.get("first_name")),
            last_name=_clip(profile.get("last_name")),
            display_name=_clip(profile.get("display_name")) or email.split("@")[0][:12],
        )
        user.set_password(uuid.uuid4().hex)
        user.is_password_autoset = True
        user.is_email_verified = False  # the placeholder is not a mailbox
        user.save()
        Profile.objects.create(user=user)
        return user
```

`adapter.py`:

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
from plane.ee.sso.config import PROVIDERS, callback_url, get_sso_config
from plane.ee.sso.identity import SubjectLoginMixin, subject_key
from plane.ee.sso.oidc import discover, verify_id_token

AZURE_ISSUER = "https://login.microsoftonline.com/{tenant}/v2.0"


def _error(code, message=None):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[code], error_message=message or code)


class SsoOauthProvider(SubjectLoginMixin, OauthAdapter):
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
        if not cfg or PROVIDERS[provider_id]["protocol"] not in ("oidc", "oauth2"):
            raise _error("SSO_NOT_CONFIGURED")
        self.provider_id = provider_id
        self.cfg = cfg
        self.nonce = nonce
        self.code_verifier = code_verifier
        self.id_claims = {}
        self.issuer = self._issuer(provider_id, cfg)
        if self.issuer:
            meta = discover(self.issuer)
            # token `iss` must equal the discovery document's issuer string exactly (may end in "/")
            self.token_issuer = meta["issuer"]
            auth_url = meta.get("authorization_endpoint")
            token_url = meta.get("token_endpoint")
            userinfo_url = meta.get("userinfo_endpoint")
            self.jwks_uri = meta.get("jwks_uri")
            if not (auth_url and token_url and self.jwks_uri):
                raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: incomplete discovery document")
        else:
            auth_url, token_url, userinfo_url = cfg["AUTH_URL"], cfg["TOKEN_URL"], cfg["USERINFO_URL"]

        redirect_uri = callback_url(request, provider_id, cfg)
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
            f"{auth_url}{'&' if '?' in auth_url else '?'}{urlencode(params)}",
            token_url,
            userinfo_url,
            cfg["CLIENT_SECRET"],
            code,
            callback=callback,
        )

    @staticmethod
    def _issuer(provider_id, cfg):
        if provider_id == "oidc":
            return cfg["ISSUER"].strip().rstrip("/")
        if provider_id == "azure_ad":
            # single tenant, v2.0 endpoint; ISSUER is an optional override (must also be a v2.0 issuer)
            return (cfg.get("ISSUER") or AZURE_ISSUER.format(tenant=cfg["TENANT_ID"].strip().lower())).strip().rstrip("/")
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
        if self.issuer:
            if not token.get("id_token"):
                raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: id_token missing")
            self.id_claims = verify_id_token(token["id_token"], self.jwks_uri, self.token_issuer, self.client_id, self.nonce)
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

    def _azure_subject(self, claims):
        """Entra best practice: identify by `oid` within the tenant `tid` (sub is per-app; UPN/e-mail are mutable)."""
        tenant = self.cfg["TENANT_ID"].strip().lower()  # get_sso_config guarantees a GUID
        if str(claims.get("tid", "")).lower() != tenant:
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: tenant mismatch")
        oid = str(claims.get("oid") or "").strip().lower()
        if not oid:
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: oid missing")
        # B2B guests: federated from another IdP (idp != iss), acct == 1, or a `#EXT#` UPN when one is present
        if (
            (claims.get("idp") and claims.get("idp") != claims.get("iss"))
            or str(claims.get("acct")) == "1"
            or "#EXT#" in str(claims.get("preferred_username") or "").upper()
        ):
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: guest accounts are not allowed")
        return f"{tenant}:{oid}"

    def set_user_data(self):
        claims = self.id_claims if self.issuer else self.get_user_response()  # OIDC: the verified id_token
        if self.provider_id == "azure_ad":
            key = self._azure_subject(claims)
        elif self.issuer:
            key = subject_key(self.token_issuer, claims.get("sub"))
        else:
            key = subject_key(self.token_url, claims.get("sub") or claims.get("id"))
        first = claims.get("given_name") or claims.get("first_name")
        last = claims.get("family_name") or claims.get("last_name")
        if not (first or last) and claims.get("name"):
            first, _, last = str(claims["name"]).partition(" ")
        self.subject_key = key
        self.profile = {
            "first_name": first,
            "last_name": last,
            "display_name": claims.get("name") or claims.get("preferred_username"),  # display only
        }

    def authenticate(self):
        self.set_token_data()
        self.set_user_data()
        return self.login_by_subject(self.subject_key, self.profile, self.cfg["ALLOW_SIGNUP"])
```

Note: `set_user_data()` here takes no argument (it overrides core's `set_user_data(self, data)`); nothing calls the base version because `authenticate()` is overridden.

- [ ] **Step 4: Run, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_identity.py plane/tests/unit/ee/sso/test_adapter.py`
If `Account` creation fails on a NOT NULL column other than `access_token`, add that field (empty string / `None`) to the `Account.objects.create` call; do not store tokens. If `user.save()` rejects the placeholder (`.invalid`) in some validator, check `plane/db/models/user.py` for an email validator and report instead of changing the domain.

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee/sso/flow.py apps/api/plane/ee/sso/identity.py apps/api/plane/ee/sso/adapter.py apps/api/plane/tests/unit/ee/sso/test_identity.py apps/api/plane/tests/unit/ee/sso/test_adapter.py
git commit -m "feat(ee): subject-keyed SSO login (OIDC, Entra single tenant, OAuth2)"
```

---

### Task 5: Views and URLs

**Files:**

- Create: `apps/api/plane/ee/sso/views.py`, `apps/api/plane/ee/sso/urls.py` (`flow.py` already exists from Task 4)
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

from plane.db.models import Account
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
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)


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
    assert Account.objects.filter(provider="sso-oidc").count() == 1
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
        host = request.session.pop("host", None) or base_host(request=request, is_app=True)
        next_path = request.session.pop("next_path", None)
        # one-time use: pop so a replayed callback fails the state check
        expected_state = request.session.pop("sso_state", None)
        nonce = request.session.pop("sso_nonce", None)
        verifier = request.session.pop("sso_verifier", None)
        code, state = request.GET.get("code"), request.GET.get("state")

        if not code or not expected_state or not secrets.compare_digest(str(state or ""), expected_state):
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
These view tests rely on `WEB_URL` / `APP_BASE_URL` being set (they come from `apps/api/.env`, created by `./setup.sh`); with neither, core's `base_host` returns `None` and redirects break.
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

### Task 6: `sso_link` — explicit linking of existing Plane users

Existing Plane users (created before SSO, by e-mail/password or another provider) are never matched automatically, because no IdP supplies a trustworthy e-mail and e-mail matching is the classic account-pre-hijacking vector. An administrator links them deliberately, once, from the shell.

**Files:**

- Create: `apps/api/plane/ee/management/__init__.py`, `apps/api/plane/ee/management/commands/__init__.py`, `apps/api/plane/ee/management/commands/sso_link.py` (license header on each)
- Test: `apps/api/plane/tests/unit/ee/sso/test_sso_link.py`

**Interfaces:**

- Consumes: `PROVIDER_IDS`, `subject_key` (Tasks 2 and 4).
- Produces: `python manage.py sso_link --provider <id> --email <existing Plane e-mail> --subject <subject> [--unlink]`. `--subject` formats: `azure_ad` → `<tenant-guid>:<oid>` (Entra portal → Users → Object ID); `oidc` → `<exact issuer>|<sub>`; `oauth2` → `<token URL>|<id>`; `saml` → `<IdP entity id>|<persistent NameID>`. It creates `Account(provider="sso-<id>", provider_account_id=<key>)` for the user; refuses when that subject is already linked to a different user or when the e-mail is unknown.

- [ ] **Step 1: Failing tests** `test_sso_link.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from plane.db.models import Account, User
from plane.ee.sso.identity import subject_key

GUID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.unit
@pytest.mark.django_db
def test_links_an_existing_user_to_an_oidc_subject():
    user = User.objects.create(email="an@corp.com", username="an")
    call_command("sso_link", provider="oidc", email="AN@corp.com", subject="https://idp.example.com|sub-1")
    account = Account.objects.get(user=user)
    assert account.provider == "sso-oidc"
    assert account.provider_account_id == subject_key("https://idp.example.com", "sub-1")


@pytest.mark.unit
@pytest.mark.django_db
def test_links_an_azure_object_id_lowercased():
    user = User.objects.create(email="an@corp.com", username="an")
    call_command("sso_link", provider="azure_ad", email="an@corp.com", subject=f"{GUID.upper()}:OID-1")
    assert Account.objects.get(user=user).provider_account_id == f"{GUID}:oid-1"


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("subject", ["oid-only", f"{GUID}:", "not-a-guid:oid-1"])
def test_azure_subject_must_be_tenant_guid_colon_oid(subject):
    User.objects.create(email="an@corp.com", username="an")
    with pytest.raises(CommandError):
        call_command("sso_link", provider="azure_ad", email="an@corp.com", subject=subject)


@pytest.mark.unit
@pytest.mark.django_db
def test_unknown_email_and_double_linking_are_refused():
    User.objects.create(email="an@corp.com", username="an")
    User.objects.create(email="bo@corp.com", username="bo")
    with pytest.raises(CommandError):
        call_command("sso_link", provider="oidc", email="nobody@corp.com", subject="https://i|s")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://i|s")
    with pytest.raises(CommandError):
        call_command("sso_link", provider="oidc", email="bo@corp.com", subject="https://i|s")


@pytest.mark.unit
@pytest.mark.django_db
def test_unlink_removes_the_link():
    user = User.objects.create(email="an@corp.com", username="an")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://i|s")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://i|s", unlink=True)
    assert not Account.objects.filter(user=user).exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_subject_may_contain_pipes_trailing_slash_is_equivalent_and_move_repoints():
    an = User.objects.create(email="an@corp.com", username="an")
    bo = User.objects.create(email="bo@corp.com", username="bo")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://t.auth0.com/|auth0|123")
    key = subject_key("https://t.auth0.com", "auth0|123")
    assert subject_key("https://t.auth0.com/", "auth0|123") == key  # trailing slash is normalised
    assert Account.objects.get(user=an).provider_account_id == key
    with pytest.raises(CommandError):
        call_command("sso_link", provider="oidc", email="bo@corp.com", subject="https://t.auth0.com|auth0|123")
    call_command("sso_link", provider="oidc", email="bo@corp.com", subject="https://t.auth0.com|auth0|123", move=True)
    assert Account.objects.get(provider_account_id=key).user_id == bo.id
```

- [ ] **Step 2: Run, expect FAIL** (`Unknown command: 'sso_link'`).

- [ ] **Step 3: Implement** `sso_link.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.core.management.base import BaseCommand, CommandError

from plane.db.models import Account, User
from plane.ee.sso.config import GUID_RE, PROVIDER_IDS
from plane.ee.sso.identity import subject_key


def _key(provider, subject):
    if provider == "azure_ad":
        tenant, _, oid = subject.strip().lower().partition(":")
        if not GUID_RE.fullmatch(tenant) or not oid:
            raise CommandError("azure_ad subject must be <tenant-guid>:<object-id>")
        return f"{tenant}:{oid}"
    # `sub` may itself contain pipes (Auth0: `auth0|123`); issuers / entity ids / URLs never do
    issuer, _, sub = subject.partition("|")
    if not issuer or not sub:
        raise CommandError("subject must be <issuer / token URL / IdP entity id>|<subject>")
    try:
        return subject_key(issuer, sub)
    except Exception as e:
        raise CommandError(str(e))


class Command(BaseCommand):
    help = "Link (or --unlink) an EXISTING Plane user to an SSO subject. E-mail is never used to link automatically."

    def add_arguments(self, parser):
        parser.add_argument("--provider", required=True, choices=PROVIDER_IDS)
        parser.add_argument("--email", required=True, help="e-mail of the existing Plane user")
        parser.add_argument(
            "--subject",
            required=True,
            help=(
                "azure_ad: <tenant-guid>:<oid>; oidc: <issuer>|<sub>; oauth2: <token URL>|<id>; "
                "saml: <IdP entity id>|<NameID>"
            ),
        )
        parser.add_argument("--unlink", action="store_true")
        parser.add_argument(
            "--move",
            action="store_true",
            help="re-point a subject that is already linked to another (e.g. auto-created) user",
        )

    def handle(self, *args, provider, email, subject, unlink=False, move=False, **options):
        user = User.objects.filter(email=email.strip().lower()).first()
        if user is None:
            raise CommandError(f"no Plane user with e-mail {email}")
        name, key = f"sso-{provider}", _key(provider, subject)
        if unlink:
            deleted, _ = Account.objects.filter(user=user, provider=name, provider_account_id=key).delete()
            self.stdout.write(self.style.SUCCESS("unlinked" if deleted else "nothing to unlink"))
            return
        account, created = Account.objects.get_or_create(
            provider=name, provider_account_id=key, defaults={"user": user, "access_token": ""}
        )
        if account.user_id != user.id:
            if not move:
                raise CommandError(
                    "that subject is already linked to a different Plane user (it logged in before being linked? "
                    "use --move to re-point it)"
                )
            account.user = user
            account.save(update_fields=["user"])
            created = None
        self.stdout.write(self.style.SUCCESS("moved" if created is None else "linked" if created else "already linked"))
```

(Remove the odd `AuthenticationException` import line above if lint complains: `subject_key` raising is caught by the broad `except Exception` already.)

- [ ] **Step 4: Run, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_sso_link.py`
Note: `PROVIDER_IDS` includes `saml` only after Phase 2; the tests above do not use it.

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee/management apps/api/plane/tests/unit/ee/sso/test_sso_link.py
git commit -m "feat(ee): sso_link command for explicit account linking"
```

---

### Task 7: `sso_join` — add an SSO user to a workspace

SSO-created users have no real e-mail, so Plane's e-mail workspace invitations cannot reach them (and an invitation to `<hash>@sso.invalid` is not something an admin can reasonably send). An administrator adds them directly.

**Files:**

- Create: `apps/api/plane/ee/management/commands/sso_join.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_sso_join.py`

**Interfaces:**

- Consumes: `sso_link._key` (Task 6), core `Workspace`, `WorkspaceMember` (verify the field names `workspace`, `member`, `role` in `apps/api/plane/db/models/workspace.py` before writing).
- Produces: `python manage.py sso_join --provider <id> --subject <subject> --workspace <slug> [--role 5|15|20]` (default 15 = member; 20 admin, 5 guest). Fails when no user has logged in / been linked with that subject yet or the workspace slug is unknown.

- [ ] **Step 1: Failing test** `test_sso_join.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from plane.db.models import Account, User, Workspace, WorkspaceMember
from plane.ee.sso.identity import subject_key


@pytest.mark.unit
@pytest.mark.django_db
def test_adds_the_user_behind_a_subject_to_a_workspace_and_updates_the_role():
    owner = User.objects.create(email="owner@corp.com", username="owner")
    workspace = Workspace.objects.create(name="W", slug="w", owner=owner)
    user = User.objects.create(email="x@sso.invalid", username="x")
    Account.objects.create(
        user=user, provider="sso-oidc", provider_account_id=subject_key("https://idp", "s1"), access_token=""
    )
    call_command("sso_join", provider="oidc", subject="https://idp|s1", workspace="w")
    assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 15
    call_command("sso_join", provider="oidc", subject="https://idp|s1", workspace="w", role=20)
    assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 20


@pytest.mark.unit
@pytest.mark.django_db
def test_unknown_subject_or_workspace_is_refused():
    owner = User.objects.create(email="owner@corp.com", username="owner")
    Workspace.objects.create(name="W", slug="w", owner=owner)
    with pytest.raises(CommandError):
        call_command("sso_join", provider="oidc", subject="https://idp|nobody", workspace="w")
    with pytest.raises(CommandError):
        call_command("sso_join", provider="oidc", subject="https://idp|nobody", workspace="missing")
```

- [ ] **Step 2: Run, expect FAIL** (`Unknown command: 'sso_join'`).

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest --ds=plane.settings.ee_test plane/tests/unit/ee/sso/test_sso_join.py`

- [ ] **Step 3: Implement** `sso_join.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.core.management.base import BaseCommand, CommandError

from plane.db.models import Account, Workspace, WorkspaceMember
from plane.ee.management.commands.sso_link import _key
from plane.ee.sso.config import PROVIDER_IDS


class Command(BaseCommand):
    help = "Add the Plane user behind an SSO subject to a workspace (e-mail invitations cannot reach SSO users)."

    def add_arguments(self, parser):
        parser.add_argument("--provider", required=True, choices=PROVIDER_IDS)
        parser.add_argument("--subject", required=True, help="same format as sso_link")
        parser.add_argument("--workspace", required=True, help="workspace slug")
        parser.add_argument("--role", type=int, choices=[5, 15, 20], default=15, help="5 guest, 15 member, 20 admin")

    def handle(self, *args, provider, subject, workspace, role=15, **options):
        account = (
            Account.objects.select_related("user")
            .filter(provider=f"sso-{provider}", provider_account_id=_key(provider, subject))
            .first()
        )
        if account is None:
            raise CommandError("no user has logged in or been linked with that subject yet")
        target = Workspace.objects.filter(slug=workspace).first()
        if target is None:
            raise CommandError(f"no workspace with slug {workspace}")
        member, created = WorkspaceMember.objects.get_or_create(
            workspace=target, member=account.user, defaults={"role": role}
        )
        if not created and member.role != role:
            member.role = role
            member.save(update_fields=["role"])
        self.stdout.write(self.style.SUCCESS("added" if created else "already a member (role updated if it differed)"))
```

- [ ] **Step 4: Run, expect PASS** (same command).

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee/management/commands/sso_join.py apps/api/plane/tests/unit/ee/sso/test_sso_join.py
git commit -m "feat(ee): sso_join command to add SSO users to workspaces"
```

---

## Known limits (carried into later phases)

- **Identity model (best-practice decision).** Identity is `(issuer, subject)`; e-mail/UPN/`preferred_username`/`email_verified` are never used (none of the IdPs send a usable e-mail, and they are mutable or unverified). Consequences: (1) JIT users have a `<hash>@sso.invalid` placeholder e-mail, so Plane e-mail notifications and e-mail workspace invites do not reach them and invites cannot auto-attach; admins add SSO users to workspaces with `sso_join` (Task 7); (2) existing Plane users are linked explicitly with `sso_link`; (3) to capture a real e-mail later, add a profile step (not in scope).
- **Azure AD (single tenant).** Tenant ID must be the tenant GUID; issuer and `tid` are always checked; identity is `tid:oid` (`sub` is per-application); B2B guests are rejected (`idp` ≠ `iss`, `acct`, `#EXT#`). Authorization belongs in Entra: enable _Assignment required_ on the enterprise application and assign users/groups. `ALLOW_SIGNUP=0` means only pre-linked (`sso_link`) users can log in.
- Discovery / JWKS / token / userinfo URLs are admin-configured and fetched without SSRF pinning (self-hosted internal IdPs are a legitimate use). Only instance admins can set them.
- With `SKIP_ENV_VAR=0` core reads configuration from environment variables only, so DB-stored `EE_SSO_*` values are ignored.
- Azure AD is single-tenant by design (Tenant ID GUID required; Issuer URL optional override, v2.0 only; no `common` / `organizations`). Group sync is out of scope. `public_origin` prefers `WEB_URL`, then `APP_BASE_URL`; if only the frontend origin is configured, set the provider's Callback URL.
- The seeded-key list is cached by core for 2 h; `seed_config` deletes that cache entry when it creates rows.
- The callback URL defaults to `<WEB_URL or APP_BASE_URL>/auth/sso/<id>/callback/` (not the Host header). Admins can override it per provider with `EE_SSO_<ID>_CALLBACK_URL` (absolute http(s) URL); the override must still route to `/auth/sso/<id>/callback/` on this API.

## Self-Review (done against the spec)

- Spec coverage for Phase 1 (also: per-provider configurable callback URL; subject-keyed identity with no e-mail anywhere; `sso_link`): plugin activation (T1), config in InstanceConfiguration (T2), OIDC with PKCE + JWKS + nonce + iss/aud/exp (T3, T4, T5), Azure AD preset (T4), generic OAuth2 (T4), `/auth/sso/providers/` + initiate/callback (T5), subject-keyed identity, JIT signup through `SubjectLoginMixin._check_signup` (provider switch + instance `ENABLE_SIGNUP`), error codes 6xxx (T1). SAML, frontend, admin UI, Docker are deferred to later plans as stated.
- Known limits to carry forward: Azure is single-tenant only (Tenant ID GUID; no `common`/`organizations`); profile data is not re-synced on later logins; discovery is cached 1h; SSO-created users have a placeholder e-mail (no e-mail notifications; use `sso_join` to add them to workspaces); `ALLOW_SIGNUP` defaults to on, so run `sso_link` for existing users **before** announcing SSO (or use `--move`).
- Type/name consistency checked: `get_sso_config`, `config_key`, `seed_config`, `list_enabled_providers`, `SsoOauthProvider` kwargs (`state`, `nonce`, `code_challenge`, `code`, `code_verifier`, `callback`), session keys `sso_state/sso_nonce/sso_verifier` are identical across tasks.
- Not verified by running: this plan was written against code reading only; Task 5's session-cookie behavior is the most likely place to need an adjustment (noted in Step 4).
