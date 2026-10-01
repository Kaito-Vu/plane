# EE SSO Plugin — Phase 5: Deployment, Upstream-Merge Guard and Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the plugin as a build-and-run unit (EE API image, compose overlays, local-dev settings), protect the "don't touch core" promise with an automated guard, and document operation and the upstream upgrade playbook.

**Architecture:** The EE API image is layered **on top of** the unmodified core image (`ARG BASE_IMAGE`), so `Dockerfile.api` / `Dockerfile.dev` stay untouched and keep merging cleanly. The plugin is switched on purely by `DJANGO_SETTINGS_MODULE` (production: `plane.settings.ee`, local: `plane.settings.ee_local`). A shell guard compares the branch against upstream and fails when any file outside an explicit allowlist (the plugin's own paths + the 6 known seam files) changed.

**Tech Stack:** Docker / Compose, POSIX sh, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-01-ee-sso-plugin-design.md`
**Depends on:** Phases 1–4.

## Global Constraints

- Do not edit `apps/api/Dockerfile.api`, `Dockerfile.dev`, `docker-compose.yml`, `docker-compose-local.yml`, any `Caddyfile`, or any existing workflow. Add new files only. (The working tree already carries unrelated uncommitted edits to several of these; never include them in this phase's commits — stage files by explicit path.)
- Production activation is `DJANGO_SETTINGS_MODULE=plane.settings.ee`; local is `plane.settings.ee_local`. Nothing else toggles the plugin.
- EE-only Python deps come from `apps/api/requirements/ee.txt` (pinned in Phase 2 Task 1); `lxml` must be built from source against the system libxml2 together with `xmlsec`.
- The allowlist (`deployments/ee/core-allowlist.txt`) is the single source of truth for "files this project may change". Adding a seam edit requires adding it there in the same commit.
- Image/service names: base image tag `plane-api-core`, EE image tag `plane-api-ee`; dev base tag `plane-api-core-dev`.

## File Structure

```
apps/api/Dockerfile.ee                     # EE layer on top of BASE_IMAGE
apps/api/plane/settings/ee_local.py        # local settings + plugin
docker-compose-ee.yml                      # overlay for docker-compose.yml
docker-compose-ee-local.yml                # overlay for docker-compose-local.yml
deployments/ee/build.sh                    # builds core base then EE images
deployments/ee/core-allowlist.txt          # paths this project may change
deployments/ee/check-core-untouched.sh     # upstream-merge guard
deployments/ee/docker-compose-mock-idp.yml # mock OIDC + SAML IdPs for smoke tests
.github/workflows/ee-guard.yml             # CI: core-untouched guard (every PR)
.github/workflows/ee-sso.yml               # CI: EE API tests (path-filtered)
deployments/ee/fork-divergence.txt         # optional: fork-wide edits tolerated by the guard
docs/ee/sso/README.md                      # operator guide + upgrade playbook
```

---

### Task 1: EE image and compose overlays

**Files:**

- Create: `apps/api/Dockerfile.ee`, `apps/api/plane/settings/ee_local.py`, `docker-compose-ee.yml`, `docker-compose-ee-local.yml`, `deployments/ee/build.sh`

**Interfaces:**

- Produces: image `plane-api-ee` (prod) built from `plane-api-core`; services `api`, `worker`, `beat-worker`, `migrator` overridden to build `Dockerfile.ee` with `DJANGO_SETTINGS_MODULE` set.

- [ ] **Step 1: Confirm the runner uses the same source-build line.** `apps/api/bin/run-ee-tests.sh` (Phase 2) must already contain the `--force-reinstall --no-deps --no-binary lxml,xmlsec -c requirements/base.txt -c requirements/ee.txt lxml xmlsec` line followed by `pip check`; a plain `pip install --no-binary lxml,xmlsec lxml xmlsec` is a no-op when the pinned `lxml` wheel from `base.txt` is already installed. If Phase 2 was implemented without it, fix it there first and re-run the Phase 2 spike.

- [ ] **Step 2: `apps/api/Dockerfile.ee`**

```dockerfile
# EE layer: adds SAML (xmlsec) and switches the plugin on. Build the core image first:
#   docker build -f apps/api/Dockerfile.api -t plane-api-core apps/api
# (dev: docker build -f apps/api/Dockerfile.dev -t plane-api-core-dev apps/api)
# The base must be in the local image store: with a docker-container buildx builder use `--load`, otherwise
# FROM tries to pull `plane-api-core` from Docker Hub.
ARG BASE_IMAGE=plane-api-core
FROM ${BASE_IMAGE}

WORKDIR /code
# Runtime libs stay; build deps are removed in the same layer.
RUN apk add --no-cache xmlsec libxml2 libxslt \
    && apk add --no-cache --virtual .ee-build gcc g++ musl-dev libffi-dev pkgconf xmlsec-dev libxml2-dev libxslt-dev \
    && pip install --no-cache-dir --force-reinstall --no-deps --no-binary lxml,xmlsec \
        -c requirements/base.txt -c requirements/ee.txt lxml xmlsec \
    && pip install --no-cache-dir -c requirements/base.txt -r requirements/ee.txt \
    && apk del .ee-build

ENV DJANGO_SETTINGS_MODULE=plane.settings.ee
```

`requirements/` is already inside the base image (`COPY requirements ./requirements` in `Dockerfile.api`, `COPY . .` in `Dockerfile.dev`), so no extra COPY is needed.

- [ ] **Step 3: `apps/api/plane/settings/ee_local.py`**

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Local development settings + EE plugin."""

from .local import *  # noqa

INSTALLED_APPS = [*INSTALLED_APPS, "plane.ee"]  # noqa
ROOT_URLCONF = "plane.ee.urls"
```

- [ ] **Step 4: `docker-compose-ee.yml`** (overlay for the production compose file)

```yaml
# Usage (from repo root, after deployments/ee/build.sh has built plane-api-core):
#   docker compose -f docker-compose.yml -f docker-compose-ee.yml build api
#   docker compose -f docker-compose.yml -f docker-compose-ee.yml up -d
x-ee-api: &ee-api
  build:
    context: ./apps/api
    dockerfile: Dockerfile.ee
    args:
      BASE_IMAGE: plane-api-core
  image: plane-api-ee # all four services share one image: build `api` once, the others reuse the tag
  environment:
    DJANGO_SETTINGS_MODULE: plane.settings.ee

services:
  api: *ee-api
  worker: *ee-api
  beat-worker: *ee-api
  migrator: *ee-api
```

- [ ] **Step 5: `docker-compose-ee-local.yml`** (overlay for the local compose file)

The local API entrypoint hard-codes `--settings=plane.settings.local` on `runserver` (overriding the env var), so the overlay rewrites it into a temp file and `exec`s that (not `| bash`: a piped script shares stdin with every child process and would not receive signals).

```yaml
# Usage:
#   docker build -f apps/api/Dockerfile.dev -t plane-api-core-dev apps/api
#   docker compose -f docker-compose-local.yml -f docker-compose-ee-local.yml up --build
x-ee-local: &ee-local
  build:
    context: ./apps/api
    dockerfile: Dockerfile.ee
    args:
      BASE_IMAGE: plane-api-core-dev
  environment:
    DJANGO_SETTINGS_MODULE: plane.settings.ee_local

services:
  api:
    <<: *ee-local
    command:
      [
        "bash",
        "-c",
        "sed 's#plane.settings.local#plane.settings.ee_local#g' ./bin/docker-entrypoint-api-local.sh > /tmp/api-ee.sh && exec bash /tmp/api-ee.sh",
      ]
  worker: *ee-local
  beat-worker: *ee-local
  migrator:
    <<: *ee-local
    command: ./bin/docker-entrypoint-migrator.sh --settings=plane.settings.ee_local
```

- [ ] **Step 6: `deployments/ee/build.sh`**

```sh
#!/bin/sh
# Build the unmodified core API image, then the EE layer on top.
# Usage: sh deployments/ee/build.sh [prod|dev]   (default prod)
set -e
MODE="${1:-prod}"
cd "$(dirname "$0")/../.."
if [ "$MODE" = "dev" ]; then
  docker build -f apps/api/Dockerfile.dev -t plane-api-core-dev apps/api
  docker compose -f docker-compose-local.yml -f docker-compose-ee-local.yml build api
else
  docker build -f apps/api/Dockerfile.api -t plane-api-core apps/api
  docker compose -f docker-compose.yml -f docker-compose-ee.yml build api
fi
```

- [ ] **Step 7: Verify the image** (smoke, not a unit test; `--env-file apps/api/.env` is required: Django needs `SECRET_KEY` and the DB variables)

Run: `sh deployments/ee/build.sh prod`
Then:

```bash
docker run --rm --env-file apps/api/.env plane-api-ee python -c "import xmlsec, lxml.etree; from onelogin.saml2.auth import OneLogin_Saml2_Auth; import django; django.setup(); from django.apps import apps; assert apps.is_installed('plane.ee'); print('ee ok')"
# plugin ON: routed (200 with a JSON list, needs a reachable DB)
docker run --rm --env-file apps/api/.env plane-api-ee python manage.py shell -c "from django.test import Client; print(Client().get('/auth/sso/providers/', HTTP_HOST='localhost').status_code)"
# plugin OFF: same image, stock settings -> the route does not exist
docker run --rm --env-file apps/api/.env -e DJANGO_SETTINGS_MODULE=plane.settings.production plane-api-ee python manage.py shell -c "from django.test import Client; print(Client().get('/auth/sso/providers/', HTTP_HOST='localhost').status_code)"
```

Expected: `ee ok`, then `200`, then `404`. If `pip` cannot build `xmlsec`, reuse the exact `apk add` package set that made the Phase 2 spike pass.

- [ ] **Step 8: Commit**

```bash
git add apps/api/Dockerfile.ee apps/api/plane/settings/ee_local.py apps/api/bin/run-ee-tests.sh docker-compose-ee.yml docker-compose-ee-local.yml deployments/ee/build.sh
git commit -m "feat(ee): EE API image and compose overlays"
```

---

### Task 2: Upstream-merge guard and CI

**Files:**

- Create: `deployments/ee/core-allowlist.txt`, `deployments/ee/check-core-untouched.sh`, `.github/workflows/ee-sso.yml`

**Interfaces:**

- Produces: `sh deployments/ee/check-core-untouched.sh` — exit 0 when every file changed between `merge-base(BASE, HEAD)` and `HEAD` matches an allowlist glob; otherwise prints the offending paths and exits 1. `BASE` env var defaults to `origin/preview`.

- [ ] **Step 1: `deployments/ee/core-allowlist.txt`** (shell `case` globs; `*` also matches `/`)

```
# Paths this project may change relative to upstream. One glob per line.
# --- plugin-owned (new files) ---
apps/api/plane/ee/*
apps/api/plane/settings/ee.py
apps/api/plane/settings/ee_test.py
apps/api/plane/settings/ee_local.py
apps/api/plane/tests/unit/ee/*
apps/api/requirements/ee.txt
apps/api/bin/run-ee-tests.sh
apps/api/Dockerfile.ee
apps/web/ee/*
apps/space/ee/*
apps/admin/ee/*
apps/admin/app/ee/*
docker-compose-ee.yml
docker-compose-ee-local.yml
deployments/ee/*
docs/ee/*
docs/superpowers/*
.github/workflows/ee-sso.yml
.github/workflows/ee-guard.yml
# --- the known core seam edits (keep this list as short as possible) ---
apps/web/hooks/oauth/extended.tsx
apps/space/hooks/oauth/extended.tsx
packages/types/src/instance/auth-ee.ts
packages/constants/src/auth/extended.ts
apps/admin/app/routes.ts
apps/admin/hooks/oauth/index.ts
```

- [ ] **Step 2: `deployments/ee/check-core-untouched.sh`**

```sh
#!/bin/sh
# Fails when the branch changes files outside the allowlist(s). Usage:
#   BASE=origin/preview sh deployments/ee/check-core-untouched.sh
# Allowlists: deployments/ee/core-allowlist.txt (always) and deployments/ee/fork-divergence.txt (optional: edits
# this fork intentionally keeps against upstream, e.g. fork-wide Docker/Caddy changes).
set -eu
cd "$(dirname "$0")/../.."
BASE="${BASE:-origin/preview}"
base_commit="$(git merge-base "$BASE" HEAD)" || { echo "cannot resolve BASE=$BASE (fetch it, with enough history)" >&2; exit 2; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
# --no-renames: a rename would otherwise list only the new path and hide the deletion of a core file.
# quotepath=off and a file (not word splitting) keep paths with spaces / non-ASCII intact.
git -c core.quotepath=off diff --name-only --no-renames "$base_commit" HEAD > "$tmp/changed"
cat deployments/ee/core-allowlist.txt > "$tmp/allow"
if [ -f deployments/ee/fork-divergence.txt ]; then cat deployments/ee/fork-divergence.txt >> "$tmp/allow"; fi
: > "$tmp/bad"
while IFS= read -r f; do
  ok=0
  while IFS= read -r pat; do
    pat="${pat%"$(printf '\r')"}" # tolerate CRLF checkouts of the allowlist
    case "$pat" in ""|"#"*) continue ;; esac
    # shellcheck disable=SC2254
    case "$f" in $pat) ok=1; break ;; esac
  done < "$tmp/allow"
  if [ "$ok" -ne 1 ]; then printf '%s\n' "$f" >> "$tmp/bad"; fi
done < "$tmp/changed"
if [ -s "$tmp/bad" ]; then
  echo "Files changed outside the EE allowlist (relative to $BASE):" >&2
  cat "$tmp/bad" >&2
  echo "Move the change into plugin-owned paths, or add it deliberately to core-allowlist.txt (seam edits) or fork-divergence.txt (fork-wide edits)." >&2
  exit 1
fi
echo "OK: only plugin-owned and allow-listed files changed."
```

- [ ] **Step 3: Test the guard** (it is the only automated protection of the main requirement, so prove both outcomes). Use a throwaway worktree so nothing in your working tree is touched or reset:

```bash
# 1) On the finished feature branch against upstream: expect exit 0 (list this fork's own divergences in fork-divergence.txt first)
BASE=<upstream>/preview sh deployments/ee/check-core-untouched.sh
# 2) Prove it fails: scratch worktree, touch a core file, commit, run, throw the worktree away
git worktree add ../p5-guard HEAD
( cd ../p5-guard && echo "" >> apps/api/plane/db/models/user.py && git commit -qam scratch \
  && BASE=<upstream>/preview sh deployments/ee/check-core-untouched.sh; echo "exit=$?" )
git worktree remove --force ../p5-guard
```

Expected: first run prints `OK: ...` and exit 0; the second lists `apps/api/plane/db/models/user.py` and `exit=1`. Also check a rename is caught: in the scratch worktree `git mv apps/api/plane/db/models/user.py apps/api/plane/ee/user_moved.py`, commit, run: it must still fail (the old path shows as a deletion).

- [ ] **Step 4: CI — two workflows.** The guard must run on _every_ PR (a PR that only edits a core file triggers no path filter), so it gets its own workflow without `paths:`.

`.github/workflows/ee-guard.yml`:

```yaml
name: EE core guard

on:
  workflow_dispatch:
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  core-untouched:
    name: Core files untouched
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - name: Check allowlist
        env:
          BASE: origin/${{ github.base_ref || 'preview' }}
        run: sh deployments/ee/check-core-untouched.sh
```

`.github/workflows/ee-sso.yml` (tests only, path-filtered):

```yaml
name: EE SSO tests

on:
  workflow_dispatch:
  pull_request:
    paths:
      - "apps/api/plane/ee/**"
      - "apps/api/plane/tests/unit/ee/**"
      - "apps/api/plane/settings/ee*.py"
      - "apps/api/requirements/**"
      - "apps/api/bin/run-ee-tests.sh"
      - "apps/api/Dockerfile.ee"
      - "docker-compose-test.yml"
      - "docker-compose-ee*.yml"
      - ".github/workflows/ee-sso.yml"

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  api-tests:
    name: EE API tests
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - name: Prepare API env file
        # ./setup.sh is non-interactive but also runs `pnpm install` for the whole monorepo (slow); the API only needs this
        run: |
          cp apps/api/.env.example apps/api/.env
          echo "SECRET_KEY=\"$(tr -dc a-z0-9 </dev/urandom | head -c50)\"" >> apps/api/.env
      - name: Run EE tests
        run: docker compose -f docker-compose-test.yml run --rm --build api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee
      - name: Tear down
        if: always()
        run: docker compose -f docker-compose-test.yml down -v
```

- [ ] **Step 4b: `deployments/ee/fork-divergence.txt`** (optional, create only if this fork keeps edits against upstream outside the plugin, e.g. the Docker/Caddy/compose changes already on this branch). Same glob format as the allowlist, one path per line with a comment saying why. Keep it short; every entry is a future merge conflict.

- [ ] **Step 5: Commit**

```bash
git add deployments/ee/core-allowlist.txt deployments/ee/check-core-untouched.sh .github/workflows/ee-guard.yml .github/workflows/ee-sso.yml
git commit -m "feat(ee): upstream-merge guard and CI workflow"
```

---

### Task 3: Operator guide, upgrade playbook and mock-IdP smoke test

**Files:**

- Create: `docs/ee/sso/README.md`, `deployments/ee/docker-compose-mock-idp.yml`

**Interfaces:**

- Produces: the written operating procedure; a mock-IdP overlay for manual smoke tests.

- [ ] **Step 1: `deployments/ee/docker-compose-mock-idp.yml`** (best effort: confirm image tags and variable names when you run it; they are not verified here)

```yaml
# Mock identity providers for manual smoke tests. Merge with the local compose files so they share the network:
#   docker compose -f docker-compose-local.yml -f docker-compose-ee-local.yml -f deployments/ee/docker-compose-mock-idp.yml up
# Add "127.0.0.1 mock-idp" to your hosts file so the browser and the API container resolve the same name.
services:
  mock-idp:
    image: ghcr.io/navikt/mock-oauth2-server:latest # OIDC issuer: http://mock-idp:8080/default (pin a tag when you run it)
    environment:
      SERVER_PORT: "8080"
      JSON_CONFIG: '{"interactiveLogin": true}'
    ports:
      - "8080:8080"
    networks:
      - dev_env

  mock-saml-idp:
    image: kristophjunge/test-saml-idp:latest # SimpleSAMLphp test IdP; users user1/user1pass, user2/user2pass
    environment:
      SIMPLESAMLPHP_SP_ENTITY_ID: http://localhost/auth/sso/saml/metadata/
      SIMPLESAMLPHP_SP_ASSERTION_CONSUMER_SERVICE: http://localhost/auth/sso/saml/acs/
    ports:
      - "8081:8080"
    networks:
      - dev_env
```

- [ ] **Step 2: `docs/ee/sso/README.md`** — write exactly this content:

````markdown
# Enterprise SSO plugin (OIDC, Azure AD, OAuth2, SAML)

A self-contained plugin: backend `apps/api/plane/ee/`, login buttons in `apps/{web,space}/ee/`, admin pages in
`apps/admin/ee/` + `apps/admin/app/ee/`. It is switched on by one setting, not by editing core.

## Enable

Production:

```bash
sh deployments/ee/build.sh prod
docker compose -f docker-compose.yml -f docker-compose-ee.yml up -d
```

Local dev: `sh deployments/ee/build.sh dev` then `docker compose -f docker-compose-local.yml -f docker-compose-ee-local.yml up`.

The migrator seeds the `EE_SSO_*` instance-configuration rows. Then open God Mode → Authentication.
To disable the plugin entirely, drop the overlay (stock `DJANGO_SETTINGS_MODULE`); the extra rows are inert.

## Configure each provider (God Mode → Authentication)

Copy the "Plane-provided details" panel values into your identity provider first.

| Provider                                       | In your IdP                                                                                                                                                                                                                   | In Plane                                                                                                                         |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| OpenID Connect                                 | Register a confidential client; redirect URI `https://<plane>/auth/sso/oidc/callback/`                                                                                                                                        | Issuer URL, client id/secret                                                                                                     |
| Microsoft (Azure AD / Entra ID), single tenant | App registration → Web redirect URI `https://<plane>/auth/sso/azure_ad/callback/`; create a client secret                                                                                                                     | Tenant ID, Client ID, Client Secret; optional Callback URL and Issuer URL override (v2.0 only)                                   |
| OAuth2                                         | Redirect URI `https://<plane>/auth/sso/oauth2/callback/`                                                                                                                                                                      | Authorization, token and user-info URLs; the user-info response must contain a stable user id (`sub` or `id`); no e-mail is used |
| SAML 2.0                                       | ACS URL `https://<plane>/auth/sso/saml/acs/` (HTTP-POST), entity id / metadata `https://<plane>/auth/sso/saml/metadata/`; NameID format **Persistent** (Entra: _Unique User Identifier_ = `user.objectid`, format Persistent) | IdP entity id, SSO URL, signing certificate; optional first/last name attribute names                                            |

Callback / ACS URL: by default it is `<WEB_URL or APP_BASE_URL>/auth/sso/<id>/callback/` (SAML: `/auth/sso/saml/acs/`), built from the API's `WEB_URL` / `APP_BASE_URL`, not from the incoming Host header, so those two variables must hold your public address. If your identity provider must use a different public URL, set "Callback URL" (SAML: "ACS URL") on the provider page; it must be an absolute `http(s)` URL that still reaches this server's `/auth/sso/...` endpoint (your reverse proxy has to route it). The right-hand panel shows the effective value.

The callback URL base is `WEB_URL`, else `APP_BASE_URL`; when only the frontend origin is configured, set the provider's Callback URL.

Options (every provider): "Allow sign-up" — on (default): a user that is not linked yet is created at first login; off: only users linked by an administrator (`sso_link`, below) can log in through this provider. The instance-wide sign-up setting still applies on top.

Behavior notes:

- Entra ID (single tenant): Tenant ID must be the tenant GUID; issuer and `tid` are always checked; the user is identified by `oid` within the tenant (never by UPN, `preferred_username` or `email`, which are mutable); B2B guests are rejected. Control who may sign in in Entra itself: enable _Assignment required_ on the enterprise application and assign users/groups. Group sync is not implemented.

- **Identity is the stable subject, never an e-mail** (none of the IdPs send one): OIDC `(issuer, sub)`, Entra `tenant:oid`, SAML persistent NameID, OAuth2 userinfo id. Users created at first login get a placeholder e-mail `<hash>@sso.invalid` (a reserved TLD that can never be a real mailbox), so Plane e-mail notifications and e-mail invitations do not reach them and an invitation can never auto-attach to them; add SSO users to workspaces directly. A pending sign-up is created only if the provider's "Allow sign-up" and the instance-wide sign-up setting are both on.
- SAML is SP-initiated only; unsolicited IdP-initiated responses are rejected. The response or assertion must be signed.
- Single logout and group/role mapping are not implemented.

## Linking existing Plane users

Existing users (created by e-mail/password or another provider) are never matched automatically. An administrator links each one once:

```bash
python manage.py sso_link --provider azure_ad --email an@corp.com --subject <tenant-guid>:<object-id>
python manage.py sso_link --provider oidc     --email an@corp.com --subject "<issuer>|<sub>"
python manage.py sso_link --provider saml     --email an@corp.com --subject "<IdP entity id>|<persistent NameID>"
```

(`--unlink` removes the link.) With a provider's "Allow sign-up" off, only linked users can log in through it.

Notes: (1) run `sso_link` for existing users **before** announcing SSO; if someone logged in first and got an auto-created user, `sso_link ... --move` re-points the link to the right user. (2) SSO-created users have no real e-mail: add them to workspaces with `python manage.py sso_join --provider <id> --subject <subject> --workspace <slug> [--role 5|15|20]`; Plane e-mail notifications do not reach them. (3) SAML requires the **persistent** NameID format; Okta, ADFS and Keycloak must be configured to send it explicitly. (4) These commands exist only when the plugin is on (`DJANGO_SETTINGS_MODULE=plane.settings.ee`).

## Troubleshooting

The browser is redirected to the login page with `error_code`:

| Code | Meaning                                                                                                                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 6000 | Provider not configured/enabled                                                                                                                                                                   |
| 6001 | Provider error (bad state/nonce/signature, token exchange failure, replay, missing subject / NameID not persistent). Details are in the API log (`plane.authentication` logger), never in the URL |
| 5015 | Sign-up is disabled (this provider's "Allow sign-up" is off, or the instance-wide setting) and this subject is not linked to a Plane user yet (see `sso_link`). Shown by the core login page      |

## Upgrading Plane from upstream

1. Merge upstream into your integration branch.
2. Run the guard against upstream: `git fetch <upstream> && BASE=<upstream>/preview sh deployments/ee/check-core-untouched.sh`. Resolve any conflict in the six seam files (listed at the bottom of `deployments/ee/core-allowlist.txt`) by keeping upstream's version and re-adding the plugin's one-line spread/import. Edits this fork keeps on purpose go in `deployments/ee/fork-divergence.txt`; CI runs the same guard on every PR.
3. Re-run the EE tests: `docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee`. A failure here usually means a core signature changed; the plugin relies on `OauthAdapter`, `Adapter`, `user_login`, `get_redirection_path`, `validate_next_path`, `get_configuration_value` and `InstanceConfiguration`.
4. Run `pnpm check` and rebuild the images with `deployments/ee/build.sh`.
5. Smoke test with the mock IdPs (below).

## Smoke test with mock IdPs

`docker compose -f docker-compose-local.yml -f docker-compose-ee-local.yml -f deployments/ee/docker-compose-mock-idp.yml up`
and add `127.0.0.1 mock-idp` to your hosts file.

- OIDC: issuer `http://mock-idp:8080/default`, any client id/secret; on the mock login page submit claims such as `{"sub":"user-1","name":"An Nguyen"}` (no e-mail needed).
- SAML: fetch `http://localhost:8081/simplesaml/saml2/idp/metadata.php`, copy the entity id, SSO URL and signing certificate into Plane; log in as `user1` / `user1pass`.
  Check: button appears on web and space login, login completes, wrong secret shows the error toast.
````

- [ ] **Step 3: Run the smoke test once** following the README and record the outcome (what ran, what was observed) in the PR description. If it cannot be run (Docker unavailable, image tags changed), say so; do not report it as passed.

- [ ] **Step 4: Commit**

```bash
git add docs/ee/sso/README.md deployments/ee/docker-compose-mock-idp.yml
git commit -m "docs(ee): SSO operator guide, upgrade playbook and mock IdP overlay"
```

---

## Self-Review (done against the spec)

- Spec coverage: EE requirements outside `base.txt` and xmlsec libs (Task 1), compose override that sets the settings module (Task 1), docs, and the "keep merging upstream" goal made enforceable (Task 2: guard on every PR, rename-safe, CRLF-safe, with an optional fork-divergence list) with an explicit playbook (Task 3). `ee_local` exists because the local entrypoint hard-codes `--settings`.
- Deviation from spec: two compose overlays (prod, local) plus a mock-IdP overlay; two workflows (guard, tests).
- Core seam files edited across the whole project: exactly six (`apps/web/hooks/oauth/extended.tsx`, `apps/space/hooks/oauth/extended.tsx`, `packages/types/src/instance/auth-ee.ts`, `packages/constants/src/auth/extended.ts`, `apps/admin/app/routes.ts`, `apps/admin/hooks/oauth/index.ts`); the allowlist and README list exactly these.
- Honest limits: nothing here has been executed. The image build (native `xmlsec`/`lxml`), the CI env-file step, the mock-IdP image variables and the rewritten local entrypoint are unproven and each has a stated verification step. Mock-IdP images are `latest` and one is archived upstream; pin tags when first run.
- Name/consistency check: tags `plane-api-core`, `plane-api-core-dev`, `plane-api-ee` consistent across Dockerfile, overlays, build script; settings modules `plane.settings.ee`, `plane.settings.ee_local`, `plane.settings.ee_test` match Phases 1/2.
