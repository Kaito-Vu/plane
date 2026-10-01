# EE SSO Plugin (OIDC, Azure AD, SAML, OAuth2) — Design

## Goal

Add enterprise SSO as a self-contained plugin that can be enabled/disabled without editing upstream core files, so the repo can keep merging from upstream `preview`.

## Scope

- Protocols: OIDC, Azure AD (OIDC preset), generic OAuth2, SAML 2.0 (SP-initiated).
- Model: instance-wide, one config per protocol (like Google/GitHub today).
- Surfaces: backend, login buttons (web + space), admin config pages.
- Out of scope: SCIM, group/role mapping, SAML SLO, per-workspace or multi-IdP routing.

## Plugin activation

- `DJANGO_SETTINGS_MODULE=plane.settings.ee` enables the plugin; unset = stock CE behavior.
- `apps/api/plane/settings/ee.py`: `from .production import *`; append `plane.ee` to `INSTALLED_APPS`; `ROOT_URLCONF = "plane.ee.urls"`.
- `apps/api/plane/ee/urls.py`: re-export `plane.urls.urlpatterns` + EE routes. No core backend file is edited.

## Backend layout (`apps/api/plane/ee/`)

```
apps.py
urls.py
sso/
  config.py            # keys, defaults, secret handling via InstanceConfiguration
  providers/
    oidc.py            # OidcAdapter(OauthAdapter): discovery, PKCE, id_token verify via JWKS
    azure_ad.py        # preset on oidc: issuer = login.microsoftonline.com/{tenant}/v2.0
    oauth2.py          # generic: manual authorize/token/userinfo endpoints + claim mapping
    saml.py            # SamlAdapter(Adapter): python3-saml, ACS + metadata
  views.py             # initiate/callback/acs/metadata, public providers list, admin config CRUD
  tests/
```

Endpoints:

- `GET /auth/sso/providers/` → `[{id,label,protocol}]` for enabled providers (public).
- `GET /auth/sso/<id>/` initiate; `GET|POST /auth/sso/<id>/callback/` (POST = SAML ACS); `GET /auth/sso/saml/metadata/`.
- `GET|PUT /api/instances/ee/sso/<id>/` admin-only config (instance admin permission reused from `plane.license`).

Behavior:

- Reuse `user_login`, `post_user_auth_workflow`, `validate_next_path`, session `state` check, and error-redirect pattern from the Gitea views.
- OIDC: authorization code + PKCE, validate `iss`, `aud`, `exp`, `nonce`, signature via JWKS; require `email_verified` when present.
- SAML: validate signature/audience/NotOnOrAfter/InResponseTo; attribute mapping for email, first/last name configurable.
- Users matched by verified email; JIT-create when `ENABLE_SIGNUP` allows; otherwise sign-up-disabled error.
- Config stored in `InstanceConfiguration` (no migration); secrets encrypted with the existing core mechanism.
- Error codes: new range (e.g. 6xxx) defined in the plugin, mapped to redirect params the same way as core.

## Frontend

- New package `packages/ee-sso`: provider-list service, login-button hook, admin config pages/forms.
- web + space: fill existing seam `hooks/oauth/extended.tsx` (only change to core files there).
- admin: no seam exists. Minimal edits: `app/routes.ts` (add routes) and `hooks/oauth/index.ts` (add modes). These two files are the only expected merge-conflict points with upstream.

## Deployment

- API Docker image: add `libxmlsec1-dev`/`libxmlsec1-openssl`, `pkg-config` and Python deps `python3-saml`, `PyJWT[crypto]` through an EE requirements file (`requirements/ee.txt`), not core `base.txt`.
- Compose override sets `DJANGO_SETTINGS_MODULE=plane.settings.ee` for api/worker/beat.

## Testing

- pytest unit tests per engine with mocked IdP (JWKS, token endpoint, signed SAML response fixtures).
- Cases: bad state, bad signature, expired token, wrong audience, unverified email, signup disabled, next_path validation.
- Frontend: typecheck/lint via `pnpm check`.

## Risks

- Admin seam edits may conflict on upstream merge (2 files, small).
- `xmlsec` native deps raise image build complexity and size.
- Upstream changes to `OauthAdapter`/`Adapter` signatures would break the plugin; covered by tests.

## Phasing

1. Backend OIDC engine + Azure AD + OAuth2 + tests
2. SAML engine + tests
3. Frontend login buttons (web/space)
4. Admin config pages
5. Docker/compose wiring and docs
