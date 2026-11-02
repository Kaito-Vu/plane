# Work Item Types — acceptance checklist

Setup: `docker compose -f docker-compose-local.yml up`, then `docker compose -f docker-compose-local.yml exec api python manage.py seed_work_item_types`. Use a project admin and a member account. API calls use the session cookie or an API token.

## 1. Six types

- [ ] Project create modal / work item modal type selector shows Epic, Feature, User Story, Task, Bug, Sub-task with coloured badges.
- [ ] `GET /api/workspaces/<slug>/projects/<pid>/work-item-types/` returns the 6 keys.

## 2. Parent rules (UI + API)

Rules: Epic<-Epic (or none), Feature<-Epic/Feature, User Story<-Feature, Task<-User Story, Bug<-Task/User Story, Sub-task<-Task/Bug.

- [ ] UI: parent picker only lists allowed parent types; non-Epic without parent shows "This work item type needs a parent."
- [ ] API: `POST .../issues/` with a Task whose parent is a Feature -> 400 `parent_type_invalid`.
- [ ] API: making an item its own ancestor -> 400 `parent_cycle`.
- [ ] Type cannot change after create (`type_immutable`).
- [ ] `pytest plane/tests/unit/ee/test_ui_rules_sync.py` passes (UI table == backend table).

## 3. Attributes (workspace library + project)

- [ ] Workspace settings > Attribute library: create a select template with options and a default.
- [ ] Project settings > Attributes: Apply from workspace library -> copy appears; its default option is pre-selected in a new work item (default remapped to the copied option).
- [ ] Editing the template afterwards does not change the project copy.
- [ ] Add/edit/hide/reorder/delete project attributes; system attributes only allow toggling Required.

## 4. Required attributes

- [ ] Mark an attribute Required; creating a work item of that type without it -> field highlighted, "Some required attributes are empty."
- [ ] Same via API -> 400 `attribute_required` with `details.missing`.

## 5. Cycle / completion rule

- [ ] Add an Epic or Feature to a cycle -> error toast (`cycle_type_not_allowed`).
- [ ] Add a Task to a cycle different from its User Story -> warning toast.
- [ ] Complete a parent with open children -> blocked, toast "N child work items are still open".

## 6. Subtree delete

- [ ] Delete/archive dialog of an item with children shows the subtree warning (direct child count).
- [ ] After delete, all descendants are gone; restore brings back only the same-batch descendants.

## 7. Intake

- [ ] Create intake item, Accept: choose type + parent + attributes, Save -> item accepted with those values (no 404).
- [ ] Decline still works.

## 8. Bulk tree

- [ ] `POST` bulk-tree endpoint with Epic > Feature > Story > Task payload creates the whole tree in one call; an invalid node rejects the whole batch.

## 9. CSV import

- [ ] Project settings > Attributes > Import CSV: upload a file with `ref,type,parent_ref,name,<attribute>` columns.
- [ ] Review table shows row errors; fix parent ref / pick an existing parent; Dry-run passes; Commit creates N items (toast).
- [ ] Empty CSV -> "The CSV has no data rows".

## 10. Columns / filters / group-by

- [ ] Display properties list attribute columns; enabling one shows values in spreadsheet/list/kanban.
- [ ] Filters: Work item type and select/member/boolean attributes (Yes/No) filter correctly.
- [ ] Group by Type (with a "None" group) and by a select/member/boolean attribute on the project work items page; groups are read-only.

## 11. i18n

- [ ] Switch language to Tiếng Việt: settings pages, modal fields, errors, import wizard are Vietnamese. Other locales fall back to English for the new keys (to be translated).
