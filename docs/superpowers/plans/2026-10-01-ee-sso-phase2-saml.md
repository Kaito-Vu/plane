# EE SSO Plugin — Phase 2: SAML 2.0 (SP-initiated) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SAML 2.0 single sign-on (SP-initiated, HTTP-Redirect request, HTTP-POST response) to the `plane.ee` plugin.

**Architecture:** `SamlProvider` subclasses core `Adapter` and wraps `python3-saml`. Config lives in the same `InstanceConfiguration` rows as Phase 1 (provider id `saml`). Because the IdP posts the response cross-site and Django's session cookie is `SameSite=Lax` (not sent on cross-site POST), pending-request state (request id, host, next_path) is kept in the Django cache under a one-time random `RelayState` token, not in the session. Assertion ids are recorded in the cache to reject replays.

**Tech Stack:** `python3-saml` (+ `xmlsec`, `lxml`), Django cache (Valkey), pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-ee-sso-plugin-design.md`
**Depends on:** `docs/superpowers/plans/2026-10-01-ee-sso-phase1-backend-oidc.md` fully implemented (uses `config.py`, `flow.py`, `views.py`, `urls.py`, `errors.py`).

## Global Constraints

- Same constraints as Phase 1: add files only (no edits to upstream-owned files), license header on every new `.py`, config keys `EE_SSO_<ID>_<FIELD>`, error codes 6000-6099, Account/medium name `sso-saml`.
- No new error codes: SAML failures use `SSO_PROVIDER_ERROR` (6001); details go to the server log only (never in the redirect).
- SP-initiated only. Unsolicited (IdP-initiated) responses are rejected because they have no stored `RelayState`.
- Replays are rejected via the assertion id cache. Relay token TTL 600 s.
- SAML dependencies live in `apps/api/requirements/ee.txt`, never in `base.txt`.
- Tests run in Docker via the wrapper added in Task 1: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh <pytest args>`.

## File Structure

```
apps/api/requirements/ee.txt                   # python3-saml (+ xmlsec pin decided in Task 1)
apps/api/bin/run-ee-tests.sh                   # installs build deps + ee.txt, runs pytest with ee_test settings
apps/api/plane/ee/sso/config.py                # (modify) add "saml" provider
apps/api/plane/ee/sso/saml.py                  # settings builder, relay store, SamlProvider
apps/api/plane/ee/sso/saml_views.py            # saml_start(), SamlAcsEndpoint, SamlMetadataEndpoint
apps/api/plane/ee/sso/views.py                 # (modify) dispatch saml in initiate
apps/api/plane/ee/sso/urls.py                  # (modify) add acs + metadata routes
apps/api/plane/tests/unit/ee/sso/saml_helpers.py   # cert/key + signed SAML response builder
apps/api/plane/tests/unit/ee/sso/test_saml_deps.py # Task 1 spike test
apps/api/plane/tests/unit/ee/sso/test_saml_provider.py
apps/api/plane/tests/unit/ee/sso/test_saml_views.py
```

---

### Task 1: Dependencies and test runner (spike)

This task proves the native stack (`xmlsec`, `lxml`, `python3-saml`) installs and signs/verifies on the project's Alpine/Python 3.14 image **before** anything is built on it. Do not start Task 2 until Step 4 passes.

**Files:**

- Create: `apps/api/requirements/ee.txt`, `apps/api/bin/run-ee-tests.sh`
- Test: `apps/api/plane/tests/unit/ee/sso/test_saml_deps.py`

**Interfaces:**

- Produces: `requirements/ee.txt` with pinned, working versions; `bin/run-ee-tests.sh`.

- [ ] **Step 1: Create `requirements/ee.txt`** (first guess; Step 3 pins what actually works)

```
# EE-only dependencies (installed by Dockerfile.ee and bin/run-ee-tests.sh)
python3-saml>=1.16.0,<2
xmlsec>=1.3.14
```

- [ ] **Step 2: Create `bin/run-ee-tests.sh`**

```sh
#!/bin/sh
# Run the EE test-suite inside the api-tests container (Alpine). Usage:
#   docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee
set -e
apk add --no-cache --virtual .ee-build gcc g++ musl-dev libffi-dev pkgconf xmlsec-dev libxml2-dev libxslt-dev
# lxml and xmlsec must be linked against the same libxml2: build both from source.
pip install --no-cache-dir --no-binary lxml,xmlsec lxml xmlsec
pip install --no-cache-dir -r requirements/ee.txt
exec pytest --ds=plane.settings.ee_test "$@"
```

- [ ] **Step 3: Write the spike test** `test_saml_deps.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest


@pytest.mark.unit
def test_saml_stack_imports_and_xmlsec_sign_verify_roundtrip():
    import xmlsec
    from lxml import etree
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # noqa: F401
    from onelogin.saml2.utils import OneLogin_Saml2_Utils

    from plane.tests.unit.ee.sso.saml_helpers import make_cert_and_key

    key_pem, cert_pem = make_cert_and_key()
    xml = '<Root xmlns="urn:test" ID="_1"><Issuer>x</Issuer></Root>'
    signed = OneLogin_Saml2_Utils.add_sign(xml, key_pem, cert_pem)
    root = etree.fromstring(signed)
    sig = xmlsec.tree.find_node(root, xmlsec.constants.NodeSignature)
    ctx = xmlsec.SignatureContext()
    ctx.key = xmlsec.Key.from_memory(cert_pem, xmlsec.constants.KeyDataFormatCertPem)
    xmlsec.tree.add_ids(root, ["ID"])
    ctx.verify(sig)  # raises on failure
```

This test imports `saml_helpers.make_cert_and_key` which is created in Step 4.

- [ ] **Step 4: Create `saml_helpers.py` with the key helper only** (the response builder is added in Task 2)

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def make_cert_and_key():
    """Return (private_key_pem, certificate_pem) as str for a throwaway self-signed IdP cert."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-idp")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return key_pem, cert.public_bytes(serialization.Encoding.PEM).decode()
```

- [ ] **Step 5: Run the spike**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/sso/test_saml_deps.py`
Expected: PASS. If it fails:

- `pip` cannot build `xmlsec`/`lxml`: confirm the `apk add` line ran; try `libxmlsec1-dev` / `xmlsec-dev` package names for the image's Alpine release (`apk search xmlsec`).
- `add_sign` rejects the PEM: pass the key/cert without the `-----BEGIN`/`END` lines (`OneLogin_Saml2_Utils.format_cert(cert_pem, False)`), then update the test and helper accordingly.
- Import error from `lxml`/`xmlsec` ABI mismatch: keep `--no-binary` for both (already in the script).
  Record the final working versions: `pip freeze | grep -i -E "saml|xmlsec|lxml"` inside the container and pin them in `requirements/ee.txt` (`python3-saml==X`, `xmlsec==Y`). Note: `lxml` is already pinned in `base.txt` (6.1.0); if the pinned `xmlsec` does not support it, stop and report instead of changing `base.txt`.

- [ ] **Step 6: Commit**

```bash
git add apps/api/requirements/ee.txt apps/api/bin/run-ee-tests.sh apps/api/plane/tests/unit/ee/sso/saml_helpers.py apps/api/plane/tests/unit/ee/sso/test_saml_deps.py
git commit -m "feat(ee): SAML dependencies, test runner and xmlsec spike"
```

---

### Task 2: SAML config entry and signed-response test builder

**Files:**

- Modify: `apps/api/plane/ee/sso/config.py` (add the `saml` entry to `PROVIDERS`)
- Modify: `apps/api/plane/tests/unit/ee/sso/saml_helpers.py` (add `build_saml_response`)
- Test: `apps/api/plane/tests/unit/ee/sso/test_saml_provider.py` (config part only in this task)

**Interfaces:**

- Produces config fields for `saml`: `IDP_ENTITY_ID`, `IDP_SSO_URL`, `IDP_X509CERT` (required), `SP_ENTITY_ID`, `ATTR_EMAIL`, `ATTR_FIRST_NAME`, `ATTR_LAST_NAME` (optional). `get_sso_config("saml")` returns a dict with those keys plus `ENABLED`, `LABEL`.
- Produces `saml_helpers.build_saml_response(*, acs_url, idp_entity_id, sp_entity_id, in_response_to, email, key_pem, cert_pem, attrs=None, assertion_id=None, valid_for=300, sign=True) -> str` returning the base64 `SAMLResponse` form value. The whole `<Response>` is signed (python3-saml accepts a signed response or a signed assertion).

- [ ] **Step 1: Write failing tests** (append to `test_saml_provider.py`; create the file with this content)

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.ee.sso.config import config_key, get_sso_config, list_enabled_providers, seed_config
from plane.license.models import InstanceConfiguration


def configure_saml(**fields):
    seed_config()
    base = {
        "ENABLED": "1",
        "IDP_ENTITY_ID": "https://idp.example.com/meta",
        "IDP_SSO_URL": "https://idp.example.com/sso",
        "IDP_X509CERT": "MIIB",
    }
    base.update(fields)
    for field, value in base.items():
        row = InstanceConfiguration.objects.get(key=config_key("saml", field))
        row.value = value
        row.save()


@pytest.mark.unit
@pytest.mark.django_db
def test_saml_requires_idp_fields_and_lists_with_protocol():
    seed_config()
    assert get_sso_config("saml") is None
    configure_saml()
    assert get_sso_config("saml")["IDP_SSO_URL"] == "https://idp.example.com/sso"
    assert {"id": "saml", "label": "SAML", "protocol": "saml"} in list_enabled_providers()


@pytest.mark.unit
@pytest.mark.django_db
def test_saml_missing_cert_is_not_configured():
    configure_saml(IDP_X509CERT="")
    assert get_sso_config("saml") is None
```

- [ ] **Step 2: Run, expect FAIL** (`DoesNotExist`: no `EE_SSO_SAML_*` rows).

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/sso/test_saml_provider.py`

- [ ] **Step 3: Add the provider** to `PROVIDERS` in `config.py` (after `oauth2`):

```python
    "saml": {
        "label": "SAML",
        "protocol": "saml",
        "fields": [
            "IDP_ENTITY_ID",
            "IDP_SSO_URL",
            "IDP_X509CERT",
            "SP_ENTITY_ID",
            "ATTR_EMAIL",
            "ATTR_FIRST_NAME",
            "ATTR_LAST_NAME",
        ],
        "required": ["IDP_ENTITY_ID", "IDP_SSO_URL", "IDP_X509CERT"],
    },
```

`SCOPE` handling already guards on `"SCOPE" in cfg`, so nothing else changes. The Phase 1 test that counts seeded rows is computed from `PROVIDERS` and keeps passing.

- [ ] **Step 4: Add `build_saml_response`** to `saml_helpers.py`

```python
import base64
import uuid
from datetime import datetime, timedelta, timezone

from onelogin.saml2.utils import OneLogin_Saml2_Utils

_FMT = "%Y-%m-%dT%H:%M:%SZ"


def build_saml_response(
    *,
    acs_url,
    idp_entity_id,
    sp_entity_id,
    in_response_to,
    email,
    key_pem,
    cert_pem,
    attrs=None,
    assertion_id=None,
    valid_for=300,
    sign=True,
):
    now = datetime.now(timezone.utc)
    issued = now.strftime(_FMT)
    not_before = (now - timedelta(minutes=1)).strftime(_FMT)
    not_after = (now + timedelta(seconds=valid_for)).strftime(_FMT)
    assertion_id = assertion_id or f"_a{uuid.uuid4().hex}"
    attrs = attrs if attrs is not None else {"firstName": "An", "lastName": "Nguyen"}
    attribute_xml = "".join(
        f'<saml:Attribute Name="{name}"><saml:AttributeValue xsi:type="xs:string">{value}</saml:AttributeValue></saml:Attribute>'
        for name, value in attrs.items()
    )
    xml = (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
        ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
        ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' ID="_r{uuid.uuid4().hex}" Version="2.0" IssueInstant="{issued}"'
        f' Destination="{acs_url}" InResponseTo="{in_response_to}">'
        f"<saml:Issuer>{idp_entity_id}</saml:Issuer>"
        '<samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
        f'<saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{issued}">'
        f"<saml:Issuer>{idp_entity_id}</saml:Issuer>"
        "<saml:Subject>"
        f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{email}</saml:NameID>'
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData NotOnOrAfter="{not_after}" Recipient="{acs_url}" InResponseTo="{in_response_to}"/>'
        "</saml:SubjectConfirmation></saml:Subject>"
        f'<saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_after}">'
        f"<saml:AudienceRestriction><saml:Audience>{sp_entity_id}</saml:Audience></saml:AudienceRestriction>"
        "</saml:Conditions>"
        f'<saml:AuthnStatement AuthnInstant="{issued}" SessionIndex="_s1"><saml:AuthnContext>'
        "<saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef>"
        "</saml:AuthnContext></saml:AuthnStatement>"
        f"<saml:AttributeStatement>{attribute_xml}</saml:AttributeStatement>"
        "</saml:Assertion></samlp:Response>"
    )
    if sign:
        signed = OneLogin_Saml2_Utils.add_sign(xml, key_pem, cert_pem)
        xml = signed.decode() if isinstance(signed, bytes) else signed
    return base64.b64encode(xml.encode()).decode()
```

- [ ] **Step 5: Run, expect PASS** (same command as Step 2).

- [ ] **Step 6: Commit**

```bash
git add apps/api/plane/ee/sso/config.py apps/api/plane/tests/unit/ee/sso/saml_helpers.py apps/api/plane/tests/unit/ee/sso/test_saml_provider.py
git commit -m "feat(ee): SAML config entry and signed-response test builder"
```

---

### Task 3: SamlProvider, relay store and settings builder

**Files:**

- Create: `apps/api/plane/ee/sso/saml.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_saml_provider.py` (append)

**Interfaces:**

- Consumes: `get_sso_config("saml")` (Task 2); core `Adapter` (`complete_login_or_signup`, `sanitize_email`); `flow.provider_error`.
- Produces (all in `plane.ee.sso.saml`):
  - `normalize_cert(value: str) -> str` — strips PEM header/footer and whitespace.
  - `acs_url(request) -> str`, `metadata_url(request) -> str`.
  - `new_relay_token() -> str`; `save_relay(token: str, data: dict) -> None`; `pop_relay(token: str) -> dict | None` (one-time).
  - `class SamlProvider(Adapter)`: `__init__(self, request, callback=None)` (raises `AuthenticationException(SSO_NOT_CONFIGURED)` if not configured); `login_url(relay_token: str) -> str`; `request_id() -> str`; `metadata_xml() -> str`; `authenticate(request_id: str) -> User`.
- Attribute lookup order for email: configured `ATTR_EMAIL`, then `email`, `mail`, `emailaddress`, `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress`, `urn:oid:0.9.2342.19200300.100.1.3`, then a NameID that contains `@`. First/last name: configured attribute, then `firstName`/`givenName`/`given_name`/`http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname`/`urn:oid:2.5.4.42` and `lastName`/`sn`/`surname`/`family_name`/`http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname`/`urn:oid:2.5.4.4`.

- [ ] **Step 1: Failing tests** (append to `test_saml_provider.py`)

```python
import pytest
from django.core.cache import cache
from django.test import RequestFactory

from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import User
from plane.ee.sso.saml import (
    SamlProvider,
    acs_url,
    new_relay_token,
    normalize_cert,
    pop_relay,
    save_relay,
)
from plane.tests.unit.ee.sso.saml_helpers import build_saml_response, make_cert_and_key

IDP = "https://idp.example.com/meta"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture(scope="module")
def keys():
    return make_cert_and_key()


@pytest.fixture
def saml(db, keys):
    configure_saml(IDP_X509CERT=keys[1])


def _acs_request(saml_response):
    request = RequestFactory().post("/auth/sso/saml/acs/", {"SAMLResponse": saml_response})
    request.META["HTTP_USER_AGENT"] = "pytest"
    return request


def _login_request():
    request = RequestFactory().get("/auth/sso/saml/")
    request.META["HTTP_USER_AGENT"] = "pytest"
    return request


def _response(keys, request, **kw):
    sp = f"http://{request.get_host()}/auth/sso/saml/metadata/"
    args = dict(
        acs_url=acs_url(request),
        idp_entity_id=IDP,
        sp_entity_id=sp,
        in_response_to="_req1",
        email="a@b.com",
        key_pem=keys[0],
        cert_pem=keys[1],
    )
    args.update(kw)
    return build_saml_response(**args)


@pytest.mark.unit
def test_normalize_cert_strips_pem_armor_and_whitespace():
    pem = "-----BEGIN CERTIFICATE-----\nAAAA\nBBBB\n-----END CERTIFICATE-----\n"
    assert normalize_cert(pem) == "AAAABBBB"


@pytest.mark.unit
def test_relay_store_is_one_time():
    token = new_relay_token()
    save_relay(token, {"request_id": "_x"})
    assert pop_relay(token) == {"request_id": "_x"}
    assert pop_relay(token) is None
    assert pop_relay("") is None


@pytest.mark.unit
def test_login_url_and_metadata(saml):
    provider = SamlProvider(_login_request())
    url = provider.login_url("tok")
    assert url.startswith("https://idp.example.com/sso?SAMLRequest=")
    assert "RelayState=tok" in url
    assert provider.request_id().startswith("ONELOGIN_") or provider.request_id()
    assert "EntityDescriptor" in provider.metadata_xml()


@pytest.mark.unit
def test_valid_signed_response_creates_user(saml, keys):
    request = _acs_request("")
    request.POST = request.POST.copy()
    request.POST["SAMLResponse"] = _response(keys, request)
    user = SamlProvider(request).authenticate("_req1")
    assert (user.email, user.first_name, user.last_name) == ("a@b.com", "An", "Nguyen")


@pytest.mark.unit
def test_existing_user_matched_by_email(saml, keys):
    existing = User.objects.create(email="a@b.com", username="x")
    request = _acs_request("")
    request.POST = request.POST.copy()
    request.POST["SAMLResponse"] = _response(keys, request)
    assert SamlProvider(request).authenticate("_req1").id == existing.id


@pytest.mark.unit
@pytest.mark.parametrize(
    "override",
    [
        {"sign": False},  # unsigned
        {"in_response_to": "_other"},  # InResponseTo mismatch
        {"sp_entity_id": "https://evil.example.com/"},  # wrong audience
        {"valid_for": -600},  # expired
    ],
)
def test_invalid_responses_rejected(saml, keys, override):
    request = _acs_request("")
    request.POST = request.POST.copy()
    request.POST["SAMLResponse"] = _response(keys, request, **override)
    with pytest.raises(AuthenticationException) as exc:
        SamlProvider(request).authenticate("_req1")
    assert exc.value.error_code == 6001


@pytest.mark.unit
def test_response_signed_by_other_key_rejected(saml, keys):
    other_key, other_cert = make_cert_and_key()
    request = _acs_request("")
    request.POST = request.POST.copy()
    request.POST["SAMLResponse"] = _response(keys, request, key_pem=other_key, cert_pem=other_cert)
    with pytest.raises(AuthenticationException):
        SamlProvider(request).authenticate("_req1")


@pytest.mark.unit
def test_assertion_replay_rejected(saml, keys):
    def attempt():
        request = _acs_request("")
        request.POST = request.POST.copy()
        request.POST["SAMLResponse"] = _response(keys, request, assertion_id="_same")
        return SamlProvider(request).authenticate("_req1")

    attempt()
    with pytest.raises(AuthenticationException) as exc:
        attempt()
    assert exc.value.error_code == 6001
```

(`_response` is called after the request exists because `Destination` and the audience derive from `request.get_host()`; with `RequestFactory` that is `testserver`.)

- [ ] **Step 2: Run, expect FAIL** (`ModuleNotFoundError: plane.ee.sso.saml`).

- [ ] **Step 3: Implement** `saml.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re
import secrets
import time

from django.core.cache import cache
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings

from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.sso import errors  # noqa: F401
from plane.ee.sso.config import get_sso_config
from plane.ee.sso.flow import provider_error

RELAY_TTL = 600
REPLAY_TTL_FALLBACK = 3600
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
NAMEID_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"

EMAIL_ATTRS = [
    "email",
    "mail",
    "emailaddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "urn:oid:0.9.2342.19200300.100.1.3",
]
FIRST_ATTRS = [
    "firstName",
    "givenName",
    "given_name",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
    "urn:oid:2.5.4.42",
]
LAST_ATTRS = [
    "lastName",
    "sn",
    "surname",
    "family_name",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
    "urn:oid:2.5.4.4",
]


def normalize_cert(value):
    return re.sub(r"-----(BEGIN|END) CERTIFICATE-----|\s+", "", value or "")


def _origin(request):
    return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"


def acs_url(request):
    return f"{_origin(request)}/auth/sso/saml/acs/"


def metadata_url(request):
    return f"{_origin(request)}/auth/sso/saml/metadata/"


def new_relay_token():
    return secrets.token_urlsafe(32)


def _relay_key(token):
    return f"ee_sso_saml_relay:{token}"


def save_relay(token, data):
    cache.set(_relay_key(token), data, RELAY_TTL)


def pop_relay(token):
    if not token:
        return None
    data = cache.get(_relay_key(token))
    if data is not None:
        cache.delete(_relay_key(token))
    return data


def build_settings(request, cfg):
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": cfg["SP_ENTITY_ID"] or metadata_url(request),
            "assertionConsumerService": {"url": acs_url(request), "binding": BINDING_POST},
            "NameIDFormat": NAMEID_EMAIL,
        },
        "idp": {
            "entityId": cfg["IDP_ENTITY_ID"],
            "singleSignOnService": {"url": cfg["IDP_SSO_URL"], "binding": BINDING_REDIRECT},
            "x509cert": normalize_cert(cfg["IDP_X509CERT"]),
        },
        # python3-saml rejects a response that carries no valid signature (response or assertion)
        # when the IdP certificate is configured, so no extra flags are needed here.
        "security": {
            "authnRequestsSigned": False,
            "wantNameIdEncrypted": False,
            "rejectDeprecatedAlgorithm": True,
        },
    }


def _prepare_request(request):
    return {
        "https": "on" if request.is_secure() else "off",
        "http_host": request.get_host(),
        "script_name": request.path,
        "get_data": request.GET.dict(),
        "post_data": request.POST.dict(),
    }


def _first(attrs, names):
    for name in names:
        values = attrs.get(name)
        if values:
            return values[0]
    return None


class SamlProvider(Adapter):
    def __init__(self, request, callback=None):
        cfg = get_sso_config("saml")
        if not cfg:
            raise AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["SSO_NOT_CONFIGURED"], error_message="SSO_NOT_CONFIGURED"
            )
        super().__init__(request, "sso-saml", callback)
        self.cfg = cfg
        self.saml_settings = build_settings(request, cfg)
        self.auth = OneLogin_Saml2_Auth(_prepare_request(request), self.saml_settings)

    def login_url(self, relay_token):
        return self.auth.login(return_to=relay_token)

    def request_id(self):
        return self.auth.get_last_request_id()

    def metadata_xml(self):
        settings = OneLogin_Saml2_Settings(self.saml_settings, sp_validation_only=True)
        xml = settings.get_sp_metadata()
        errors = settings.validate_metadata(xml)
        if errors:
            raise provider_error(f"SSO_PROVIDER_ERROR: invalid SP metadata {errors}")
        return xml.decode() if isinstance(xml, bytes) else xml

    def authenticate(self, request_id):
        self.auth.process_response(request_id=request_id)
        if self.auth.get_errors() or not self.auth.is_authenticated():
            # reason is logged only; never put it in the redirect (it can leak IdP/SP details)
            self.logger.warning("SAML response rejected: %s %s", self.auth.get_errors(), self.auth.get_last_error_reason())
            raise provider_error()
        self._reject_replay()
        self.set_user_data()
        return self.complete_login_or_signup()

    def _reject_replay(self):
        assertion_id = self.auth.get_last_assertion_id()
        not_on_or_after = self.auth.get_last_assertion_not_on_or_after()
        ttl = max(int(not_on_or_after - time.time()), 60) if not_on_or_after else REPLAY_TTL_FALLBACK
        if assertion_id and not cache.add(f"ee_sso_saml_assertion:{assertion_id}", 1, ttl):
            self.logger.warning("SAML assertion replay rejected")
            raise provider_error()

    def set_user_data(self):
        attrs = self.auth.get_attributes()
        configured = self.cfg.get("ATTR_EMAIL")
        nameid = self.auth.get_nameid() or ""
        email = _first(attrs, ([configured] if configured else []) + EMAIL_ATTRS) or (nameid if "@" in nameid else None)
        if not email:
            raise provider_error("SSO_PROVIDER_ERROR: no email in SAML response")
        first = _first(attrs, ([self.cfg["ATTR_FIRST_NAME"]] if self.cfg.get("ATTR_FIRST_NAME") else []) + FIRST_ATTRS)
        last = _first(attrs, ([self.cfg["ATTR_LAST_NAME"]] if self.cfg.get("ATTR_LAST_NAME") else []) + LAST_ATTRS)
        super().set_user_data(
            {
                "email": email,
                "user": {
                    "provider_id": nameid or email,
                    "first_name": first or "",
                    "last_name": last or "",
                    "avatar": "",
                    "is_password_autoset": True,
                },
            }
        )
```

Notes for the implementer: `Adapter.set_user_data(self, data)` stores `self.user_data = data`; our override takes no argument and delegates, matching Phase 1. `token_data` stays `None`, so core's `complete_login_or_signup` skips creating an `Account` row (SAML has no tokens) — intended. In the test `test_login_url_and_metadata` the assertion on `request_id()` only checks it is non-empty (`or` branch is deliberately loose because the id format is library-defined).

- [ ] **Step 4: Run, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/sso/test_saml_provider.py`
If `test_invalid_responses_rejected[valid_for=-600]` passes only because Conditions are in the past — that is the intended "expired" case. If any "valid" test fails with a `Destination`/`Audience`/`Recipient` mismatch, print `provider.auth.get_last_error_reason()` and fix the helper values (not the provider's strict settings).

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee/sso/saml.py apps/api/plane/tests/unit/ee/sso/test_saml_provider.py
git commit -m "feat(ee): SAML provider with relay store and replay protection"
```

---

### Task 4: SAML views and routes

**Files:**

- Create: `apps/api/plane/ee/sso/saml_views.py`
- Modify: `apps/api/plane/ee/sso/views.py` (dispatch `saml` in `SsoInitiateEndpoint`), `apps/api/plane/ee/sso/urls.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_saml_views.py`

**Interfaces:**

- Consumes: `SamlProvider`, `new_relay_token`, `save_relay`, `pop_relay` (Task 3); `flow.redirect_error`, `flow.provider_error`, `flow.complete_login` (Phase 1).
- Produces:
  - `saml_start(request, host, next_path) -> HttpResponseRedirect` (to the IdP, or app root with error params). Stores relay data `{"request_id", "host", "next_path"}`.
  - `GET /auth/sso/saml/` (via the existing initiate route), `POST /auth/sso/saml/acs/` (CSRF-exempt), `GET /auth/sso/saml/metadata/` (XML, public).

- [ ] **Step 1: Failing tests** `test_saml_views.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from plane.db.models import User
from plane.ee.sso.config import config_key, seed_config
from plane.ee.sso.saml import acs_url
from plane.license.models import Instance, InstanceConfiguration
from plane.tests.unit.ee.sso.saml_helpers import build_saml_response, make_cert_and_key

IDP = "https://idp.example.com/meta"


@pytest.fixture(scope="module")
def keys():
    return make_cert_and_key()


@pytest.fixture
def setup(db, keys):
    cache.clear()
    Instance.objects.create(
        instance_name="t", instance_id="i", current_version="1", last_checked_at=timezone.now(), is_setup_done=True
    )
    seed_config()
    for field, value in {
        "ENABLED": "1",
        "IDP_ENTITY_ID": IDP,
        "IDP_SSO_URL": "https://idp.example.com/sso",
        "IDP_X509CERT": keys[1],
    }.items():
        row = InstanceConfiguration.objects.get(key=config_key("saml", field))
        row.value = value
        row.save()


def _error_code(response):
    return parse_qs(urlparse(response["Location"]).query).get("error_code", [None])[0]


def _start(client):
    response = client.get("/auth/sso/saml/")
    assert response.status_code == 302
    relay = parse_qs(urlparse(response["Location"]).query)["RelayState"][0]
    return relay, cache.get(f"ee_sso_saml_relay:{relay}")["request_id"]


def _post_acs(client, keys, relay, request_id, **kw):
    sp = "http://testserver/auth/sso/saml/metadata/"
    from django.test import RequestFactory

    args = dict(
        acs_url=acs_url(RequestFactory().get("/")),
        idp_entity_id=IDP,
        sp_entity_id=sp,
        in_response_to=request_id,
        email="new@corp.com",
        key_pem=keys[0],
        cert_pem=keys[1],
    )
    args.update(kw)
    return client.post("/auth/sso/saml/acs/", {"SAMLResponse": build_saml_response(**args), "RelayState": relay})


@pytest.mark.unit
def test_metadata_is_public_xml(setup):
    response = Client().get("/auth/sso/saml/metadata/")
    assert response.status_code == 200
    assert "xml" in response["Content-Type"]
    assert b"EntityDescriptor" in response.content


@pytest.mark.unit
def test_initiate_redirects_to_idp_and_saves_relay(setup):
    relay, request_id = _start(Client())
    assert relay and request_id


@pytest.mark.unit
def test_initiate_unconfigured_redirects_with_error(db):
    seed_config()
    Instance.objects.create(
        instance_name="t", instance_id="i", current_version="1", last_checked_at=timezone.now(), is_setup_done=True
    )
    response = Client().get("/auth/sso/saml/")
    assert response.status_code == 302 and _error_code(response) == "6000"


@pytest.mark.unit
def test_acs_success_without_csrf_token_or_session(setup, keys):
    start_client = Client()
    relay, request_id = _start(start_client)
    # a fresh client models the IdP's cross-site POST: no session cookie, no CSRF token
    response = _post_acs(Client(enforce_csrf_checks=True), keys, relay, request_id)
    assert response.status_code == 302 and _error_code(response) is None
    assert User.objects.filter(email="new@corp.com").exists()


@pytest.mark.unit
def test_acs_rejects_unknown_relay_state(setup, keys):
    response = _post_acs(Client(), keys, "bogus", "_x")
    assert _error_code(response) == "6001"


@pytest.mark.unit
def test_acs_relay_is_single_use(setup, keys):
    relay, request_id = _start(Client())
    assert _error_code(_post_acs(Client(), keys, relay, request_id)) is None
    assert _error_code(_post_acs(Client(), keys, relay, request_id)) == "6001"


@pytest.mark.unit
def test_acs_rejects_bad_signature(setup, keys):
    relay, request_id = _start(Client())
    response = _post_acs(Client(), keys, relay, request_id, sign=False)
    assert _error_code(response) == "6001"
    assert not User.objects.filter(email="new@corp.com").exists()
```

- [ ] **Step 2: Run, expect FAIL** (404 / import errors).

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/sso/test_saml_views.py`

- [ ] **Step 3: Implement** `saml_views.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from plane.authentication.adapter.error import AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.ee.sso.flow import complete_login, provider_error, redirect_error
from plane.ee.sso.saml import SamlProvider, new_relay_token, pop_relay, save_relay


def saml_start(request, host, next_path):
    try:
        provider = SamlProvider(request)
        token = new_relay_token()
        url = provider.login_url(token)
        save_relay(token, {"request_id": provider.request_id(), "host": host, "next_path": next_path})
        return HttpResponseRedirect(url)
    except AuthenticationException as e:
        return redirect_error(host, e, next_path)


@method_decorator(csrf_exempt, name="dispatch")
class SamlAcsEndpoint(View):
    """Receives the IdP's cross-site POST. CSRF-exempt by necessity; integrity comes from the
    signed response, the one-time RelayState and the InResponseTo check."""

    def post(self, request):
        relay = pop_relay(request.POST.get("RelayState", ""))
        if not relay:
            return redirect_error(base_host(request=request, is_app=True), provider_error())
        host, next_path = relay["host"], relay.get("next_path")
        try:
            provider = SamlProvider(request, callback=post_user_auth_workflow)
            user = provider.authenticate(relay["request_id"])
            return complete_login(request, user, host, next_path)
        except AuthenticationException as e:
            return redirect_error(host, e, next_path)


class SamlMetadataEndpoint(View):
    def get(self, request):
        try:
            return HttpResponse(SamlProvider(request).metadata_xml(), content_type="text/xml")
        except AuthenticationException:
            return HttpResponse(status=404)
```

Modify `views.py` — add the import and dispatch right after the instance-configured check inside `SsoInitiateEndpoint.get` (before the `try:`):

```python
from plane.ee.sso.saml_views import saml_start
...
        if provider_id == "saml":
            return saml_start(request, host, next_path)
```

Modify `urls.py` — add before the `<str:provider_id>/` routes (literal paths must win):

```python
from .saml_views import SamlAcsEndpoint, SamlMetadataEndpoint
...
    path("saml/acs/", SamlAcsEndpoint.as_view(), name="ee-sso-saml-acs"),
    path("saml/metadata/", SamlMetadataEndpoint.as_view(), name="ee-sso-saml-metadata"),
```

- [ ] **Step 4: Run all EE tests, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee`
Expected: Phase 1 + Phase 2 tests pass. In `test_acs_success_without_csrf_token_or_session` the session cookie written on the ACS response is irrelevant to the assertion; only the redirect and the created user are checked.

- [ ] **Step 5: Core suite still unchanged**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m unit`
Expected: same pass count as the baseline.

- [ ] **Step 6: Commit**

```bash
git add apps/api/plane/ee/sso apps/api/plane/tests/unit/ee/sso
git commit -m "feat(ee): SAML initiate, ACS and metadata endpoints"
```

---

## Self-Review (done against the spec)

- Spec coverage: SAML signature/audience/NotOnOrAfter/InResponseTo validation (Task 3 tests), attribute mapping configurable (Task 3), ACS + metadata + SP-initiated login (Task 4), JIT signup via core adapter (inherited), config in `InstanceConfiguration` (Task 2), deps outside `base.txt` (Task 1). SLO, IdP-initiated, encrypted assertions, signed AuthnRequests are out of scope.
- Deviation from spec: ACS path is `/auth/sso/saml/acs/` (POST), not `<id>/callback/`. Spec text to be updated.
- Decision recorded: pending state is cached (not in session) because of `SameSite=Lax` session cookies.
- Known risks: (1) native `xmlsec`/`lxml` stack on Alpine + Python 3.14 is unproven until Task 1 Step 5 passes; (2) `add_sign` argument format may need adjustment; (3) `_prepare_request` host/port behind proxies relies on `SECURE_PROXY_SSL_HEADER` (already set in production settings) — verify with a real IdP in Phase 5 smoke test; (4) not run here — written from code reading and library knowledge.
- Names checked across tasks: `normalize_cert`, `acs_url`, `metadata_url`, `new_relay_token`, `save_relay`, `pop_relay`, `SamlProvider.login_url/request_id/metadata_xml/authenticate`, `saml_start`, relay data keys `request_id/host/next_path`.
