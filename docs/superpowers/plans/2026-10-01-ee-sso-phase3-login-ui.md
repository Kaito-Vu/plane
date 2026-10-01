# EE SSO Plugin — Phase 3: Login Buttons (web + space) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the enabled SSO providers as sign-in/sign-up buttons on the web and space login pages, with a working space (public views) login flow and readable errors, without adding any new workspace package.

**Architecture:** The frontend asks the public endpoint `GET /auth/sso/providers/` (Phase 1) and renders one `TOAuthOption` per provider through the existing `extended.tsx` seam that upstream already merges with the core OAuth options. All new frontend code lives in a new `ee/sso/` folder per app (no new `package.json`, so `pnpm-lock.yaml` is untouched). Space needs its own backend entry (`/auth/sso/spaces/<id>/`) because core logs space users in with `is_space=True` and redirects to the space host.

**Tech Stack:** Django (plugin), React Router apps `web` and `space`, SWR, `@plane/blocks/toast`, `@makeplane/propel/icons`.

**Spec:** `docs/superpowers/specs/2026-10-01-ee-sso-plugin-design.md`
**Depends on:** Phase 1 (and Phase 2 for SAML buttons; the UI works with whatever providers the endpoint returns).

## Global Constraints

- Core files edited in this phase are limited to the pre-existing EE seams: `apps/web/hooks/oauth/extended.tsx`, `apps/space/hooks/oauth/extended.tsx`, `packages/types/src/instance/auth-ee.ts`, `packages/constants/src/auth/extended.ts`. Everything else is new files under `apps/web/ee/`, `apps/space/ee/`, `apps/api/plane/ee/`, `apps/api/plane/tests/unit/ee/`.
- No new workspace packages, no changes to any `package.json` or `pnpm-lock.yaml`.
- Every new `.ts/.tsx` starts with the 5-line license block comment used in core (`/** Copyright (c) 2023-present Plane Software, Inc. and contributors ... */`).
- Login-medium ids are exactly `sso-oidc`, `sso-azure_ad`, `sso-oauth2`, `sso-saml` (must match `Account.provider` / `user.last_login_medium` written by the backend).
- Error codes handled by the UI: `6000`, `6001`, `6002`.
- Imports use the `@/` alias (maps to each app root), `@plane/*` for shared packages, `@makeplane/propel/*` for primitives.
- Verification commands: `pnpm --filter web check:types`, `pnpm --filter space check:types`, `pnpm --filter web check:lint`, `pnpm --filter space check:lint`, `pnpm --filter web check:format`, `pnpm --filter space check:format`. (The apps have no unit-test runner; behavior is verified by type-checks plus the manual check in Task 5.)

## File Structure

```
apps/api/plane/ee/sso/flow.py                   # (modify) target-aware complete_login + host_for
apps/api/plane/ee/sso/views.py                  # (modify) target kwarg on initiate/callback
apps/api/plane/ee/sso/saml_views.py             # (modify) carry target through relay + ACS
apps/api/plane/ee/sso/urls.py                   # (modify) spaces/<id>/ route
apps/api/plane/tests/unit/ee/sso/test_space_target.py
packages/types/src/instance/auth-ee.ts          # (modify) TExtendedLoginMediums
packages/constants/src/auth/extended.ts         # (modify) labels
apps/web/ee/sso/use-sso-oauth-config.tsx        # new hook
apps/web/ee/sso/microsoft-logo.svg              # new asset
apps/web/hooks/oauth/extended.tsx               # (modify, seam)
apps/space/ee/sso/use-sso-oauth-config.tsx
apps/space/ee/sso/microsoft-logo.svg
apps/space/hooks/oauth/extended.tsx             # (modify, seam)
```

---

### Task 1: Backend — space target

**Files:**

- Modify: `apps/api/plane/ee/sso/flow.py`, `views.py`, `saml_views.py`, `urls.py`
- Test: `apps/api/plane/tests/unit/ee/sso/test_space_target.py`

**Interfaces:**

- Consumes: Phase 1 `flow.complete_login(request, user, host, next_path)`, views; Phase 2 `saml_start`, `SamlAcsEndpoint`.
- Produces:
  - `flow.host_for(request, target: str) -> str` (`"space"` → `base_host(request, is_space=True)`, else `is_app=True`).
  - `flow.complete_login(request, user, host, next_path, target="app")` — for `target == "space"`: `user_login(..., is_space=True)` and redirect to `f"{host}{validated_next_path_or_empty}"` (same shape as core's space callbacks).
  - Route `GET /auth/sso/spaces/<provider_id>/` → initiate with `target="space"`. The (single) callback URL stays `/auth/sso/<id>/callback/`; the target is remembered in the session (`sso_target`) for OAuth providers and in the relay data (`target`) for SAML.
  - `saml_start(request, host, next_path, target="app")`.

- [ ] **Step 1: Failing tests** `test_space_target.py`

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

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
    cache.clear()
    Instance.objects.create(
        instance_name="t", instance_id="i", current_version="1", last_checked_at=timezone.now(), is_setup_done=True
    )
    seed_config()
    for field, value in {"ENABLED": "1", "CLIENT_ID": "cid", "CLIENT_SECRET": "sek", "ISSUER": ISS}.items():
        row = InstanceConfiguration.objects.get(key=config_key("oidc", field))
        row.value = encrypt_data(value) if field == "CLIENT_SECRET" else value
        row.save()
    mocker.patch("plane.ee.sso.oidc.requests.get").return_value.json.return_value = META


def _run(client, start_path, mocker, make_id_token):
    q = parse_qs(urlparse(client.get(start_path)["Location"]).query)
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {
        "access_token": "at",
        "id_token": make_id_token(nonce=q["nonce"][0], email="sp@corp.com"),
    }
    return client.get(f"/auth/sso/oidc/callback/?code=c&state={q['state'][0]}")


@pytest.mark.unit
def test_space_initiate_logs_in_as_space_user(setup, mocker, make_id_token):
    spy = mocker.patch("plane.ee.sso.flow.user_login")
    response = _run(Client(), "/auth/sso/spaces/oidc/?next_path=/issues/abc", mocker, make_id_token)
    assert response.status_code == 302
    assert spy.call_args.kwargs["is_space"] is True
    assert "is_app" not in spy.call_args.kwargs
    assert response["Location"].endswith("/issues/abc")


@pytest.mark.unit
def test_app_initiate_still_logs_in_as_app_user(setup, mocker, make_id_token):
    spy = mocker.patch("plane.ee.sso.flow.user_login")
    _run(Client(), "/auth/sso/oidc/", mocker, make_id_token)
    assert spy.call_args.kwargs["is_app"] is True


@pytest.mark.unit
def test_space_initiate_unknown_provider_redirects_with_error(setup):
    response = Client().get("/auth/sso/spaces/nope/")
    assert response.status_code == 302
    assert parse_qs(urlparse(response["Location"]).query)["error_code"] == ["6000"]
```

- [ ] **Step 2: Run, expect FAIL** (404 for `/auth/sso/spaces/...`).

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee/sso/test_space_target.py`

- [ ] **Step 3: Implement.**

`flow.py` — replace `complete_login` and add `host_for` (add `from plane.authentication.utils.host import base_host` to the imports):

```python
def host_for(request, target="app"):
    if target == "space":
        return base_host(request=request, is_space=True)
    return base_host(request=request, is_app=True)


def complete_login(request, user, host, next_path, target="app"):
    """Log the user in and redirect. Mirrors core: app users get the redirection path, space users
    land on the space host (+ validated next_path)."""
    if target == "space":
        user_login(request=request, user=user, is_space=True)
        path = str(validate_next_path(next_path)) if next_path else ""
        return HttpResponseRedirect(f"{host}{path}")
    user_login(request=request, user=user, is_app=True)
    path = str(validate_next_path(next_path)) if next_path else get_redirection_path(user=user)
    return HttpResponseRedirect(urljoin(host, path))
```

`views.py`:

- import `host_for` from `plane.ee.sso.flow`.
- `SsoInitiateEndpoint.get(self, request, provider_id, target="app")`: replace `host = base_host(request=request, is_app=True)` with `host = host_for(request, target)`; after `request.session["host"] = host` add `request.session["sso_target"] = target`; change the SAML dispatch to `return saml_start(request, host, next_path, target)`.
- `SsoCallbackEndpoint.get`: after reading `next_path`, add `target = request.session.pop("sso_target", "app")`; fallback host becomes `host_for(request, target)`; `callback=post_user_auth_workflow if target == "app" else None` (core's space callbacks pass no workflow); final line `return complete_login(request, user, host, next_path, target)`.
- Remove the now-unused `base_host` import from `views.py` if nothing else uses it.

`saml_views.py`:

- `def saml_start(request, host, next_path, target="app")`: relay data becomes `{"request_id": ..., "host": host, "next_path": next_path, "target": target}`.
- `SamlAcsEndpoint.post`: `target = relay.get("target", "app")`; `SamlProvider(request, callback=post_user_auth_workflow if target == "app" else None)`; `return complete_login(request, user, host, next_path, target)`. The early error redirect for a missing relay keeps using the app host.

`urls.py` — add before the `<str:provider_id>/` routes:

```python
    path("spaces/<str:provider_id>/", SsoInitiateEndpoint.as_view(), {"target": "space"}, name="ee-sso-space-initiate"),
```

- [ ] **Step 4: Run all EE tests, expect PASS**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee`

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/ee/sso apps/api/plane/tests/unit/ee/sso
git commit -m "feat(ee): SSO space login target"
```

---

### Task 2: Login-medium types and labels (seam files)

These two files exist upstream as empty extension points (`never` / `{}`), so editing them is the intended extension mechanism.

**Files:**

- Modify: `packages/types/src/instance/auth-ee.ts`
- Modify: `packages/constants/src/auth/extended.ts`

**Interfaces:**

- Produces: `TExtendedLoginMediums = "sso-oidc" | "sso-azure_ad" | "sso-oauth2" | "sso-saml"`; `EXTENDED_LOGIN_MEDIUM_LABELS` entries for each, used by `LOGIN_MEDIUM_LABELS` (workspace member list "last login medium" column).

- [ ] **Step 1: Edit `auth-ee.ts`** — replace `export type TExtendedLoginMediums = never;` with:

```ts
export type TExtendedLoginMediums = "sso-oidc" | "sso-azure_ad" | "sso-oauth2" | "sso-saml";
```

Leave `TExtendedInstanceAuthenticationModeKeys = never` untouched (the admin app in Phase 4 deliberately does not widen it).

- [ ] **Step 2: Edit `extended.ts`** — replace `= {};` with:

```ts
export const EXTENDED_LOGIN_MEDIUM_LABELS: Record<TExtendedLoginMediums, string> = {
  "sso-oidc": "OpenID Connect",
  "sso-azure_ad": "Microsoft",
  "sso-oauth2": "OAuth2",
  "sso-saml": "SAML",
};
```

- [ ] **Step 3: Verify** (the apps read these packages through their built `dist`, so rebuild first)

Run: `pnpm turbo run build --filter=@plane/types --filter=@plane/constants`
Run: `pnpm --filter @plane/types check:types && pnpm --filter @plane/constants check:types && pnpm --filter web check:types`
Expected: all pass. If `Record<TLoginMediums, string>` in `packages/constants/src/auth/index.ts` now fails, it means a medium id is missing from the labels — fix the labels, not the type.

- [ ] **Step 4: Commit**

```bash
git add packages/types/src/instance/auth-ee.ts packages/constants/src/auth/extended.ts
git commit -m "feat(ee): SSO login medium types and labels"
```

---

### Task 3: Web login hook

**Files:**

- Create: `apps/web/ee/sso/use-sso-oauth-config.tsx`, `apps/web/ee/sso/microsoft-logo.svg`
- Modify: `apps/web/hooks/oauth/extended.tsx`

**Interfaces:**

- Consumes: `TOAuthConfigs`, `TOAuthOption` from `@plane/types` (`{ id, text, icon, onClick, enabled? }`); `API_BASE_URL` from `@plane/constants`; `GET /auth/sso/providers/` returning `[{id, label, protocol}]`.
- Produces: `useSsoOAuthConfig(oauthActionText: string, basePath?: string): TOAuthConfigs` (default `basePath = "/auth/sso/"`); the seam `useExtendedOAuthConfig(oauthActionText)` returns it.

- [ ] **Step 1: Create the logo** `apps/web/ee/sso/microsoft-logo.svg`

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 23 23" width="23" height="23"><path fill="#f35325" d="M1 1h10v10H1z"/><path fill="#81bc06" d="M12 1h10v10H12z"/><path fill="#05a6f0" d="M1 12h10v10H1z"/><path fill="#ffba08" d="M12 12h10v10H12z"/></svg>
```

- [ ] **Step 2: Create the hook** `use-sso-oauth-config.tsx`

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { setToast } from "@plane/blocks/toast";
import { API_BASE_URL } from "@plane/constants";
import { KeyOutline } from "@makeplane/propel/icons";
import type { TOAuthConfigs, TOAuthOption } from "@plane/types";
// assets
import microsoftLogo from "./microsoft-logo.svg?url";

type TSsoProvider = { id: string; label: string; protocol: "oidc" | "oauth2" | "saml" };

const SSO_ERROR_MESSAGES: Record<string, string> = {
  "6000": "Single sign-on is not configured. Contact your administrator.",
  "6001": "Sign-in with your identity provider failed. Please try again.",
  "6002": "Your identity provider did not verify your email address.",
};

const fetchProviders = async (): Promise<TSsoProvider[]> => {
  const response = await fetch(`${API_BASE_URL}/auth/sso/providers/`, { credentials: "include" });
  if (!response.ok) return [];
  return (await response.json()) as TSsoProvider[];
};

export const useSsoOAuthConfig = (oauthActionText: string, basePath: string = "/auth/sso/"): TOAuthConfigs => {
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next_path");
  const errorCode = searchParams.get("error_code");
  // Plugin not installed (404) or API down: resolve to no providers instead of surfacing an error.
  const { data: providers } = useSWR("EE_SSO_PROVIDERS", () => fetchProviders().catch(() => []), {
    revalidateOnFocus: false,
  });

  useEffect(() => {
    const message = errorCode ? SSO_ERROR_MESSAGES[errorCode] : undefined;
    if (message) setToast({ type: "error", title: "Single sign-on failed", message });
  }, [errorCode]);

  const oAuthOptions: TOAuthOption[] = (providers ?? []).map((provider) => ({
    id: `sso-${provider.id}`,
    text: `${oauthActionText} with ${provider.label}`,
    icon:
      provider.id === "azure_ad" ? (
        <img src={microsoftLogo} height={18} width={18} alt="Microsoft Logo" />
      ) : (
        <KeyOutline className="h-[18px] w-[18px] text-tertiary" />
      ),
    onClick: () => {
      const query = nextPath ? `?next_path=${encodeURIComponent(nextPath)}` : "";
      window.location.assign(`${API_BASE_URL}${basePath}${provider.id}/${query}`);
    },
    enabled: true,
  }));

  return { isOAuthEnabled: oAuthOptions.length > 0, oAuthOptions };
};
```

- [ ] **Step 3: Wire the seam** — replace the body of `apps/web/hooks/oauth/extended.tsx` (keep its license header):

```tsx
// plane imports
import type { TOAuthConfigs } from "@plane/types";
// ee imports
import { useSsoOAuthConfig } from "@/ee/sso/use-sso-oauth-config";

export const useExtendedOAuthConfig = (oauthActionText: string): TOAuthConfigs => useSsoOAuthConfig(oauthActionText);
```

- [ ] **Step 4: Verify**

Run: `pnpm --filter web check:types && pnpm --filter web check:lint && pnpm --filter web check:format`
Expected: PASS. If `*.svg?url` is not typed, mirror the import style of `apps/web/hooks/oauth/core.tsx` (`import giteaLogo from "@/app/assets/logos/gitea-logo.svg?url"`) — the same ambient module declaration covers files outside `app/assets`. If `KeyOutline` does not take `className`, copy how `apps/admin/hooks/oauth/core.tsx` renders it. If oxfmt reports formatting, run `pnpm --filter web fix:format`.

- [ ] **Step 5: Commit**

```bash
git add apps/web/ee apps/web/hooks/oauth/extended.tsx
git commit -m "feat(ee): SSO login buttons on web"
```

---

### Task 4: Space login hook

**Files:**

- Create: `apps/space/ee/sso/use-sso-oauth-config.tsx`, `apps/space/ee/sso/microsoft-logo.svg`
- Modify: `apps/space/hooks/oauth/extended.tsx`

**Interfaces:**

- Same as Task 3. The space seam currently exports `useExtendedOAuthConfig = (_oauthActionText: string): TOAuthConfigs => ({...})` as an arrow with an object body; keep that export name.

- [ ] **Step 1: Copy** `apps/web/ee/sso/microsoft-logo.svg` and `use-sso-oauth-config.tsx` to `apps/space/ee/sso/` unchanged. They only depend on `next/navigation`, `swr`, `@plane/*` and `@makeplane/propel`, all of which `space` already has. (Duplicated rather than shared on purpose: a shared package would require `package.json` + lockfile edits in core.)

- [ ] **Step 2: Wire the seam** — `apps/space/hooks/oauth/extended.tsx` (keep its header):

```tsx
// plane imports
import type { TOAuthConfigs } from "@plane/types";
// ee imports
import { useSsoOAuthConfig } from "@/ee/sso/use-sso-oauth-config";

export const useExtendedOAuthConfig = (oauthActionText: string): TOAuthConfigs =>
  useSsoOAuthConfig(oauthActionText, "/auth/sso/spaces/");
```

- [ ] **Step 3: Verify**

Run: `pnpm --filter space check:types && pnpm --filter space check:lint && pnpm --filter space check:format`
Expected: PASS (fix formatting with `pnpm --filter space fix:format`).

- [ ] **Step 4: Commit**

```bash
git add apps/space/ee apps/space/hooks/oauth/extended.tsx
git commit -m "feat(ee): SSO login buttons on space"
```

---

### Task 5: End-to-end check against a mock IdP (manual)

No automated frontend runner exists, so this task is a recorded manual check. Skip only if the Docker dev stack cannot be started; say so in the PR instead of claiming it passed.

- [ ] **Step 1: Start the stack with the plugin** (needs Phase 5 compose override; if Phase 5 is not done yet, set `DJANGO_SETTINGS_MODULE=plane.settings.ee` on the api/worker/migrator services of the local compose and run `docker compose -f docker-compose-local.yml up --build`, then `python manage.py migrate` in the migrator).
- [ ] **Step 2: Start a mock OIDC IdP** (e.g. `docker run --rm -p 8080:8080 ghcr.io/navikt/mock-oauth2-server`; confirm the current image tag first). Its issuer is `http://localhost:8080/default`.
- [ ] **Step 3: Configure** through the core admin configuration API (the admin UI arrives in Phase 4). With an instance-admin session cookie:

```bash
curl -X PATCH http://localhost:8000/api/instances/configurations/ -H 'Content-Type: application/json' \
  -d '{"EE_SSO_OIDC_ENABLED":"1","EE_SSO_OIDC_LABEL":"Mock IdP","EE_SSO_OIDC_CLIENT_ID":"plane","EE_SSO_OIDC_CLIENT_SECRET":"secret","EE_SSO_OIDC_ISSUER":"http://localhost:8080/default"}'
```

- [ ] **Step 4: Verify** — open the web login page: a "Sign in with Mock IdP" button shows below the core providers; clicking it goes through the mock IdP and lands logged in. Repeat on a space (public) page. Break it on purpose (wrong secret) and confirm the "Single sign-on failed" toast appears. Check the workspace member list shows "Mock IdP"-medium label as "OpenID Connect".
- [ ] **Step 5: Record** the results (what was run, what was seen) in the PR description.

---

## Self-Review (done against the spec)

- Spec coverage: login buttons on web + space via the existing seam (Tasks 3–4), space login flow (Task 1), readable errors (hook effect, no core `authErrorHandler` edit), last-login medium labels (Task 2).
- Deviations from spec: no `packages/ee-sso` (would force `package.json`/lockfile edits in core; code lives in `apps/{web,space}/ee/sso/` instead); error toasts are handled in the EE hook rather than by extending core's `authErrorHandler`. Update the spec accordingly.
- Placeholder scan: none; commands and code are concrete. The mock-IdP image tag is flagged as "confirm current tag".
- Type consistency: provider shape `{id,label,protocol}` matches Phase 1/2 `list_enabled_providers`; option ids `sso-<id>` match the medium ids in Task 2; `saml_start(request, host, next_path, target)` and `complete_login(..., target)` match across Task 1 files.
- Not verified by running: written from code reading only. Highest-risk spots: `?url` import typing for assets outside `app/`, `KeyOutline` props, relay `target` plumbing in the SAML ACS path.
