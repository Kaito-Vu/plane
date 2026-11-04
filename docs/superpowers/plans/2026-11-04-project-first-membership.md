# Project-first membership Implementation Plan

> **Superseded by rulings during execution** (the body below is the original plan, not rewritten):
> - Task 2: no ee `partial_update` override; role changes use core behavior unchanged.
> - Task 6: the `post_save` safety net provisions on row CREATION only (not on every active save).
> - Review Focus: POST of an already-active member returns 400 `ALREADY_MEMBER` instead of an idempotent re-add; role 20 requires a workspace Admin caller (`ROLE_NOT_ALLOWED`).
> - Task 8 actual files: `add-members-and-refresh.ts`, `fetch-candidates.ts`, `allowed-roles.ts`, `member-add-error.ts`, `invites-cache.ts` (pure helpers with vitest tests) in place of `__tests__/modal.test.tsx` (no React test harness in `apps/web`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project admins add existing users straight to a project (a workspace membership is created automatically); every email-invite path is closed behind a god-mode switch that defaults to OFF.

**Architecture:** Backend lives in `apps/api/plane/ee/project_members/`; ee URLs are included before core (`plane/urls.py:19-25`), so subclassed views shadow core routes with zero core edits. Web lives in `apps/web/ee/project-members/` and `apps/admin/ee/god-mode/`, with a few allow-listed one-line core seams.

**Tech Stack:** Django/DRF, celery beat, pytest-django (`apps/api/plane/tests`), React + MobX + vitest (`apps/web`), react-router (`apps/admin`).

**Spec:** `docs/superpowers/specs/2026-11-04-project-first-membership-design.md` (decisions D1-D9, invariants I1-I6). Read it first.

## Global Constraints

- Core edits only in the allow-listed seams of Task 9 and Task 10; every other change under `plane/ee/`, `apps/web/ee/`, `apps/admin/ee/`, tests, docs.
- ws role granted by the service: project 20/15 -> 15, project 5 -> 5; never 20; never lower an existing active role (reactivation resets to the mapped role).
- Ineligible target (unknown id, inactive, bot): HTTP 400 `{"error": "...", "code": "USER_NOT_ELIGIBLE"}`, identical for all causes; nothing written.
- Closed invite paths: HTTP 410 `{"error": "...", "code": "INVITES_DISABLED"}` while `ALLOW_EXTERNAL_INVITES` is not `"1"`; flag stored in `InstanceConfiguration` key `ALLOW_EXTERNAL_INVITES`, default OFF.
- Search: `GET workspaces/<slug>/projects/<project_id>/members/search/?q=`; project Admin only; `q` >= 3 chars (else 400); max 10 results; throttle `30/min` per user; fields `id, display_name, avatar_url, email` (email masked `a***@domain`); excludes inactive, bots, active members of that project.
- Only ws Admin (20) may create projects (app `POST projects/` and API v1).
- Workspace creation stays core's `DISABLE_WORKSPACE_CREATION=1`; god-mode creates workspaces.
- Work happens in the worktree `D:\working\02.ETC\plane-pfm` on branch `feat/project-first-membership`. Stage and commit only the files a task names (`git add <paths>`; `git commit -m ...`). Never `git add -A`.
- Test command (from `apps/api`): `docker compose -f ../../docker-compose-test.yml run --rm --build api-tests pytest plane/tests/contract/app/ee/<file> -v`; web: `pnpm --filter web vitest run <file>`.

## Review Focus

- Malformed `member_id` (not a UUID) or empty `members` list -> 400, never 500.
- Adding a user who is already an active project member -> no duplicate rows, no error from the service.
- Search `q` containing `%`, `_`, uppercase, trailing spaces -> matched literally / case-insensitively on email, trimmed.
- A user in two workspaces loses only the workspace whose last project they left; ws Admin and `Workspace.owner` are never disabled.
- Missing or malformed `ALLOW_EXTERNAL_INVITES` row (`"True"`, `""`, absent) -> treated as OFF.

## File Structure

- Create `apps/api/plane/ee/project_members/{__init__,services,views,urls,signals,permissions,invites,tasks}.py` — one responsibility each (see tasks).
- Create `apps/api/plane/ee/migrations/0004_delete_pending_invites.py`.
- Modify `apps/api/plane/ee/{apps.py,urls.py,api_urls.py}`, `apps/api/plane/ee/god_mode/{urls,views}.py`.
- Create tests `apps/api/plane/tests/contract/app/ee/test_project_members_*.py`, `apps/api/plane/tests/unit/ee/test_project_members_services.py`.
- Create `apps/web/ee/project-members/**`, `apps/admin/ee/god-mode/external-invites-page.tsx`.
- Seams (Tasks 9-10): `apps/web/components/project/member-list.tsx`, `apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/members/page.tsx`, `apps/admin/app/routes.ts`, `apps/admin/hooks/use-sidebar-menu/index.ts`, i18n index, `deployments/ee/core-allowlist.txt`.

---

### Task 1: Provisioning service

**Files:**
- Create: `apps/api/plane/ee/project_members/__init__.py` (empty), `services.py`
- Test: `apps/api/plane/tests/unit/ee/test_project_members_services.py`

**Interfaces:**
- Produces:
  - `class UserNotEligible(Exception)`
  - `PROJECT_TO_WORKSPACE_ROLE: dict[int, int] = {20: 15, 15: 15, 5: 5}`
  - `eligible_users(user_ids: Iterable[str]) -> list[User]` — raises `UserNotEligible` if any id is malformed, unknown, inactive or bot.
  - `provision_workspace_member(workspace: Workspace, user: User, project_role: int) -> WorkspaceMember`
  - `deprovision_if_orphan(workspace_id, user_id) -> bool` (True if a row was disabled)
  - `sweep_orphan_workspace_members() -> int` (count disabled)

- [ ] **Step 1: Write failing tests** `test_provision_creates_member_role_15_for_project_admin`, `test_provision_guest_maps_to_5`, `test_provision_never_downgrades_active_ws_admin` (role stays 20), `test_provision_reactivates_inactive_row_with_mapped_role`, `test_provision_is_idempotent` (one row after two calls), `test_eligible_users_rejects_unknown_inactive_bot_and_malformed`, `test_deprovision_disables_when_no_active_project_member`, `test_deprovision_skips_ws_admin_and_owner_and_users_with_other_projects`, `test_deprovision_only_affects_given_workspace`, `test_sweep_disables_orphans_after_project_soft_delete`.
- [ ] **Step 2:** Run the file; expect FAIL (`ModuleNotFoundError`).
- [ ] **Step 3:** Implement the five names above in `services.py`. Both provision and deprovision `select_for_update()` the `WorkspaceMember` row first, inside `transaction.atomic`. "Orphan" = no `ProjectMember(is_active=True)` whose `project` is not soft-deleted.
- [ ] **Step 4:** Run the file; expect PASS.
- [ ] **Step 5:** Commit `feat(ee): workspace membership provisioning service`.

### Task 2: Project member views shadow (app API)

**Files:**
- Create: `ee/project_members/views.py` (`EeProjectMemberViewSet`), `ee/project_members/urls.py`
- Modify: `ee/urls.py` (append `path("", include("plane.ee.project_members.urls"))`)
- Test: `tests/contract/app/ee/test_project_members_app.py`

**Interfaces:**
- Consumes: Task 1 service.
- Produces: `class EeProjectMemberViewSet(ProjectMemberViewSet)` overriding `create(self, request, slug, project_id)` and `partial_update(self, request, slug, project_id, pk)`; `urls.py` re-registers core's three project-member routes (`members/`, `members/<uuid:pk>/`, `members/leave/` from `app/urls/project.py:74-91`) with the same method maps and names, pointing at the ee class.

- [ ] **Step 1: Write failing tests** (fixtures: `session_client`, `workspace`, `create_user` + a project with `create_user` as project Admin): `test_route_resolves_to_ee_view` (`resolve(...).func.cls is EeProjectMemberViewSet`), `test_core_create_signature_unchanged` (`inspect.signature(ProjectMemberViewSet.create.__wrapped__)` equals `(instance, request, slug, project_id)`), `test_add_existing_user_without_ws_membership_creates_both_rows` (201; `WorkspaceMember.role == 15`; user sees workspace via `GET /api/users/me/workspaces/`), `test_add_unknown_user_400_user_not_eligible_and_no_rows`, `test_add_inactive_and_bot_user_same_error_shape`, `test_malformed_member_id_400`, `test_empty_members_400`, `test_project_admin_of_other_project_403`, `test_guest_role_gets_ws_guest`, `test_already_active_member_no_duplicate`, `test_patch_role_to_member_raises_ws_guest_to_15`, `test_patch_role_20_by_non_ws_admin_keeps_core_403` (core limit at `member.py:271`), `test_add_ws_admin_target_as_member_returns_core_400` (core limit `member.py:83`).
- [ ] **Step 2:** Run; expect FAIL.
- [ ] **Step 3:** Implement. `create`: validate `members` list shape (400 on empty/non-list), `eligible_users` -> 400 `USER_NOT_ELIGIBLE`; then in one `transaction.atomic` call `provision_workspace_member` for each, then `return super().create(request, slug, project_id)`. `partial_update`: when `role` present and target is active, provision for the requested role, then `super()`.
- [ ] **Step 4:** Run; expect PASS. **Step 5:** Commit `feat(ee): project member create provisions workspace membership`.

### Task 3: Member search endpoint

**Files:** Modify `ee/project_members/views.py` (`ProjectMemberSearchEndpoint`, `MemberSearchThrottle`), `ee/project_members/urls.py`; Test `tests/contract/app/ee/test_project_members_search.py`.

**Interfaces:** `class MemberSearchThrottle(UserRateThrottle)` with `rate = "30/min"`, `scope = "ee_member_search"`; `ProjectMemberSearchEndpoint(BaseAPIView).get(request, slug, project_id)` guarded by `allow_permission([ROLE.ADMIN])`; route `members/search/` registered BEFORE `members/<uuid:pk>/`.

- [ ] **Step 1: Write failing tests:** `test_short_query_400` (`q="ab"`), `test_non_admin_403`, `test_returns_whitelisted_keys_only` (`{"id","display_name","avatar_url","email"}`), `test_email_masked` (`a***@domain`), `test_excludes_bot_inactive_and_existing_members`, `test_cap_10`, `test_wildcards_are_literal` (`q="%%%"` returns none), `test_case_insensitive_trimmed` (`"  ALICE@X.COM "`), `test_31st_call_429` (clear the throttle cache in the test).
- [ ] **Step 2:** Run; FAIL. **Step 3:** Implement with `User.objects.filter(email__icontains=q.strip())` (Django escapes `%`/`_`) or `display_name__icontains`, ordered by email, `[:10]`; log `slug/project_id/actor/len(q)` at INFO. **Step 4:** PASS. **Step 5:** Commit `feat(ee): project member search endpoint`.

### Task 4: API v1 member create shadow

**Files:** Modify `ee/project_members/views.py` (`EeProjectMemberListCreateAPIEndpoint`), `ee/api_urls.py`; Test `tests/contract/api/test_project_members_v1.py` (follow `api_key_client` fixture).

**Interfaces:** subclass of `plane.api.views.member.ProjectMemberListCreateAPIEndpoint` overriding `post(self, request, slug, project_id)`; route string identical to `api/urls/member.py:18` with `.as_view(http_method_names=["get", "post"])`, name `project-members`.

- [ ] **Step 1: Write failing tests:** `test_v1_route_resolves_to_ee_view`, `test_v1_add_unknown_user_400_user_not_eligible`, `test_v1_add_existing_user_provisions_ws_member`.
- [ ] **Step 2-5:** Run/FAIL, implement (read the user id from the same payload key core's `ProjectMemberSerializer` uses, call `eligible_users` + `provision_workspace_member`, then `super().post`), PASS, commit `feat(ee): v1 project member create provisions workspace membership`.

### Task 5: Only ws Admin creates projects

**Files:** Create `ee/project_members/permissions.py` (`install()`), modify `ee/project_members/views.py` (`EeProjectViewSet`), `ee/project_members/urls.py`, `ee/apps.py` (`ready()` calls `permissions.install()` after `access.install()`); Test `tests/contract/app/ee/test_project_creation_gate.py`.

**Interfaces:** `EeProjectViewSet(ProjectViewSet).create(self, request, slug)` -> 403 `{"error": ...}` unless active ws role 20, else `super().create`; shadow route `workspaces/<str:slug>/projects/` with `{"get": "list", "post": "create"}`, name `project`. `install()` replaces `ProjectBasePermission.has_permission` with a wrapper that returns False for `POST` unless ws role 20 and otherwise delegates to the original.

- [ ] **Step 1: Write failing tests:** `test_ws_member_cannot_create_project_403`, `test_ws_admin_can_create_project`, `test_v1_ws_member_cannot_create_project`, `test_list_route_still_works_for_member`, `test_base_permission_signature_unchanged` (`inspect.signature` of the saved original `has_permission` is `(self, request, view)`).
- [ ] **Step 2-5:** Run/FAIL, implement, PASS, commit `feat(ee): restrict project creation to workspace admins`.

### Task 6: Deprovision on removal, sweep task

**Files:** Create `ee/project_members/signals.py`, `ee/project_members/tasks.py`; modify `ee/apps.py` (`ready()` imports signals and registers beat); Test `tests/contract/app/ee/test_project_members_deprovision.py`.

**Interfaces:** `@receiver(post_save, sender=ProjectMember)` — if `is_active` false call `deprovision_if_orphan(workspace_id, member_id)`; if active call `provision_workspace_member` (safety net). `@shared_task def ee_sweep_orphan_workspace_members() -> int` wraps `sweep_orphan_workspace_members`. In `ready()`: `from plane.celery import app; app.conf.beat_schedule["ee-sweep-orphan-workspace-members"] = {"task": "plane.ee.project_members.tasks.ee_sweep_orphan_workspace_members", "schedule": crontab(minute=0)}`.

- [ ] **Step 1: Write failing tests:** `test_destroy_last_project_disables_ws_member_and_hides_workspace`, `test_destroy_with_other_project_keeps_ws_member`, `test_leave_last_project_disables`, `test_readd_reactivates`, `test_ws_admin_and_owner_never_disabled`, `test_project_soft_delete_then_sweep_disables`, `test_beat_entry_registered` (`"ee-sweep-orphan-workspace-members" in app.conf.beat_schedule`).
- [ ] **Step 2-5:** Run/FAIL, implement, PASS, commit `feat(ee): deprovision workspace member when last project is left`.
- [ ] **Step 6 (manual, noted in PR):** confirm celery beat picks up the entry by starting beat once (`DatabaseScheduler` syncs `app.conf.beat_schedule`).

### Task 7: External-invites switch and closed invite paths

**Files:** Create `ee/project_members/invites.py`, `ee/migrations/0004_delete_pending_invites.py`; modify `ee/project_members/urls.py`, `ee/api_urls.py`, `ee/urls.py`, `ee/god_mode/{urls,views}.py`; Test `tests/contract/app/ee/test_external_invites.py`.

**Interfaces:**
- `external_invites_enabled() -> bool` (True only if the `InstanceConfiguration` value is exactly `"1"`).
- `gated(core_view_cls, *methods) -> type` — subclass whose listed methods return the 410 body unless the flag is on, else `super()`.
- Shadowed (copy path, method map and name from the core urls): app `workspaces/<slug>/invitations/` (POST), `workspaces/<slug>/invitations/<pk>/join/`, `users/me/workspaces/invitations/` (POST), `workspaces/<slug>/projects/<project_id>/invitations/` (POST), `workspaces/<slug>/projects/<project_id>/join/<pk>/`; v1 `invitations/` router create (`api/urls/invite.py`).
- `GET external-invites/` (authenticated) -> `{"enabled": bool}` in `ee/urls.py`; `GET|PATCH instances/external-invites/` (god-mode only, body `{"enabled": bool}`, `InstanceAdminPermission`) in `god_mode`.
- Migration 0004: `RunPython` hard-deleting every `WorkspaceMemberInvite` and `ProjectMemberInvite` row (bypass soft delete); reverse is a no-op.

- [ ] **Step 1: Write failing tests:** `test_flag_default_off`, `test_malformed_values_are_off` (`"True"`, `""`, row absent), `test_each_shadowed_endpoint_410_when_off_and_creates_no_workspace_member`, `test_forwards_to_core_when_on` (workspace invite create returns core's response), `test_status_endpoint_any_user`, `test_toggle_god_mode_only` (ws Admin 403, god-mode 200), `test_migration_hard_deletes_invites` (call the migration function directly), `test_login_with_old_accepted_invite_creates_no_row`.
- [ ] **Step 2-5:** Run/FAIL, implement, PASS, commit `feat(ee): god-mode switch for external invites, close invite paths`.

### Task 8: Web modal and members-page gate

**Files:** Create `apps/web/ee/project-members/{services/project-member-search.service.ts,search-query.ts,send-project-invitation-modal.tsx,use-external-invites-enabled.ts,__tests__/search-query.test.ts,__tests__/modal.test.tsx}`; i18n keys.

**Interfaces:**
- `MIN_SEARCH_CHARS = 3`; `normalizeQuery(q: string): string` (trim); `shouldSearch(q: string): boolean`.
- `ProjectMemberSearchService.search(workspaceSlug, projectId, q): Promise<{id: string; display_name: string; avatar_url: string; email: string}[]>` calling the Task 3 route.
- `SendProjectInvitationModal` — same props as `apps/web/components/project/send-project-invitation-modal.tsx` (`isOpen, onClose, onSuccess?, projectId, workspaceSlug`); copy that file, header comment names its origin commit; candidates come from a 300 ms debounced `search`; default role 15; role options capped by the admin's project role; submits through the existing `bulkAddMembersToProject`; shows a "no user found" empty state (copy via i18n).
- `useExternalInvitesEnabled(): boolean` (fetches `GET /api/external-invites/`, defaults false while loading).

- [ ] **Step 1: Write failing tests:** `shouldSearch("ab") === false`, `shouldSearch("abc") === true`, `normalizeQuery("  A@b.c ") === "A@b.c"`; modal: no request below 3 chars, one request after debounce, default role 15, selecting a result then submit calls `bulkAddMembersToProject` with `{members: [{member_id, role: 15}]}`.
- [ ] **Step 2-5:** run/FAIL, implement, PASS, commit `feat(web): project member modal with instance user search`.
- [ ] **Step 6:** add `en` and `vi-VN` strings (precedent: `packages/i18n/src/locales/en/work-item-type.json` and how it is registered); follow the `translate` skill; other locales fall back.

### Task 9: Web core seams and allowlist

**Files:** Modify `apps/web/components/project/member-list.tsx:22` (import the ee modal), `apps/web/app/(all)/[workspaceSlug]/(settings)/settings/(workspace)/members/page.tsx` (hide the invite button unless `useExternalInvitesEnabled()`), `deployments/ee/core-allowlist.txt` (add every core file in this task).

- [ ] **Step 1:** Edit the two web files (one import line; one condition on the button).
- [ ] **Step 2:** Run `scripts/check-core-allowlist.sh preview`; expect the listed core files flagged until added.
- [ ] **Step 3:** Add the files to the allowlist; rerun; expect exit 0.
- [ ] **Step 4:** Run the Task 8 web tests and `pnpm check:types --filter web`; expect PASS.
- [ ] **Step 5:** Commit `feat(web): wire ee member modal, hide workspace invite button`.

### Task 10: Admin switch page

**Files:** Create `apps/admin/ee/god-mode/external-invites-page.tsx`; modify `apps/admin/app/routes.ts` (one `route("external-invites", "../ee/god-mode/external-invites-page.tsx")` beside the `admin-access` precedent), `apps/admin/hooks/use-sidebar-menu/index.ts` (one menu entry), allowlist.

**Interfaces:** page reads/writes `GET|PATCH /api/instances/external-invites/`; a single toggle with a one-sentence explanation; toast on success/error.

- [ ] **Step 1:** Write a vitest/RTL test if the admin app has the harness; otherwise state in the PR that the page is verified manually. **Step 2:** Implement following `apps/admin/ee/god-mode/admin-access-page.tsx`. **Step 3:** `pnpm check:types --filter admin`; expect PASS. **Step 4:** Commit `feat(admin): god-mode external invites switch`.

### Task 11: Operations, docs, full verification

**Files:** Modify `.env.prod.example` (add `DISABLE_WORKSPACE_CREATION=1` with a comment), create `docs/superpowers/specs/project-first-membership-ops.md` (operator note: ENABLE_SIGNUP/Entra requirement, switch semantics, login-first rule, known limits from spec §6).

- [ ] **Step 1:** Run the full ee backend tests and the previously existing suites touching invites/members (`pytest plane/tests -k "invite or member or project" -v`); fix or update core tests that assumed invite endpoints work (state each in the commit body).
- [ ] **Step 2:** `scripts/check-core-allowlist.sh preview` exits 0; `pnpm check` passes.
- [ ] **Step 3:** Browser acceptance (spec §3): ws Admin creates a project and adds a user who never had a workspace membership; that user logs in and sees only the workspace; ws Member cannot create a project; remove the user -> workspace disappears; switch OFF -> workspace/project invite returns 410 and the invite button is hidden; switch ON -> core invite works.
- [ ] **Step 4:** Commit `docs: operator notes for project-first membership`.

---

## Self-review notes

- Spec coverage: D1/D4/I1-I5 Tasks 1-2, 4; D2 Task 5; D3 Task 11; D5 Task 6; D6/D8 Task 7, 10; D7 Task 3; D9 Tasks 8-9; §5 tests mapped per task; web unit tests in Task 8.
- Resolved in plan: app project creation does not use `ProjectBasePermission`, hence shadow plus patch (spec D2 amended); search minimum is 3 characters everywhere.
- Open for the implementer to confirm: that celery beat reads `app.conf.beat_schedule` entries added in `ready()` (Task 6 step 6); whether the admin app has a test harness (Task 10).
