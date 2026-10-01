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
