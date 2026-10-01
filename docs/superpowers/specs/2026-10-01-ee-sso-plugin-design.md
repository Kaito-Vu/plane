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
- OIDC: authorization code + PKCE, validate `iss`, `aud`, `exp`, `nonce`, signature via JWKS (identity is `(iss, sub)`; see the Identity model section).
- SAML: validate signature/audience/NotOnOrAfter/InResponseTo; attribute mapping for email, first/last name configurable.
- Users are matched by the stable subject through `Account`; JIT-create when the provider switch and `ENABLE_SIGNUP` allow; otherwise sign-up-disabled error.
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
- Cases: bad state, bad signature, expired token, wrong audience, signup disabled, unlinked subject, next_path validation.
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

## Revisions decided while planning (supersede the sections above where they differ)

- No `packages/ee-sso` workspace package (it would force `package.json` / `pnpm-lock.yaml` edits in core). Frontend code lives in `apps/{web,space,admin}/ee/` (+ `apps/admin/app/ee/` for routes).
- No EE admin config endpoint: the plugin seeds `EE_SSO_*` rows into `InstanceConfiguration` and the admin UI reuses core's `PATCH /api/instances/configurations/`.
- Flat backend layout `plane/ee/sso/*.py` (no `providers/` directory); SAML ACS is `POST /auth/sso/saml/acs/`; space login uses `/auth/sso/spaces/<id>/`.
- Per-provider configurable callback URL (`EE_SSO_<ID>_CALLBACK_URL`, SAML: ACS URL); default is built from `WEB_URL`/`APP_BASE_URL`, not the Host header.
- SAML pending state is kept in the cache under a one-time RelayState (session cookies are SameSite=Lax and are not sent on the IdP's cross-site POST).
- Admin pages: one route per provider (`/authentication/sso-<id>`); only two core files are edited in admin (`app/routes.ts`, `hooks/oauth/index.ts`). Six core seam files in total (see Phase 5 allowlist).
- Error toasts are handled in the EE login hook (codes 6000-6001); core's `authErrorHandler` is not edited.

## Identity model (supersedes every e-mail-matching statement above)

No IdP sends a usable e-mail, and best practice (OIDC Core `sub`, Entra `oid`+`tid`, SAML persistent NameID, OAuth 2.0 Security BCP) says never to identify or link users by e-mail. Identity is the stable subject: OIDC `(iss, sub)`, Entra `tid:oid`, SAML persistent NameID, OAuth2 userinfo id. E-mail claims, `email_verified`, `preferred_username` and UPN are never read as identity. First-login users get a `<hash>@sso.invalid` placeholder e-mail; existing Plane users are linked explicitly by an admin (`manage.py sso_link`). Access control for Entra lives in Entra (_Assignment required_); group sync is out of scope. Default scope is `openid profile`.
