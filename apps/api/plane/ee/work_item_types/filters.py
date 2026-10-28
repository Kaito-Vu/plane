"""Filter / group-by by issue type and attribute (spec §8). Core seams call in here only
when a key is ours, so requests without `type` / `attribute:<id>` keys pay nothing.

Lookups go through the typed AttributeValue columns, served by the
(attribute, value_*) indexes in plane.ee.models.value (no JSON scan)."""

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import OuterRef, Q, Subquery
from django.utils.dateparse import parse_date

from plane.db.models import ProjectMember
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.models import Attribute, AttributeValue

from .constants import AGILE_SOURCE
from .exceptions import WorkItemValidationError

PREFIX = "attribute:"
GROUP_PREFIX = "attr_"
TYPE_KEYS = {"type", "type__in"}
GROUPABLE = {"select", "member", "boolean"}
_COLUMN = {
    "text": "value_text",
    "textarea": "value_text",
    "url": "value_text",
    "number": "value_number",
    "date": "value_datetime",
    "datetime": "value_datetime",
    "boolean": "value_boolean",
    "select": "value_option_id",
    "multi_select": "value_option_id",
    "member": "value_uuid",
    "multi_member": "value_uuid",
}


def _bad(code: str, message: str, **details) -> WorkItemValidationError:
    return WorkItemValidationError(code, message, details)


def _list(raw: Any) -> list:
    return list(raw) if isinstance(raw, (list, tuple)) else [v for v in str(raw).split(",") if v != ""]


def _uuid(raw: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise _bad("invalid_filter", "Expected a UUID", value=str(raw)) from None


def _number(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        raise _bad("invalid_filter", "Expected a number", value=str(raw)) from None


def _date(raw: Any):
    value = parse_date(str(raw))
    if value is None:
        raise _bad("invalid_filter", "Expected a date (YYYY-MM-DD)", value=str(raw))
    return value


def _boolean(raw: Any) -> bool:
    text = str(raw).lower()
    if text not in ("true", "false"):
        raise _bad("invalid_filter", "Expected true or false", value=str(raw))
    return text == "true"


def build_attribute_q(attribute: Attribute, op: str, raw: Any) -> Q:
    """Q on Issue: issues whose value for `attribute` matches `op`/`raw`."""
    ft = attribute.field_type
    column = _COLUMN[ft]
    if ft in ("text", "textarea", "url") and op == "contains":
        lookup = {f"{column}__icontains": str(raw)}
    elif ft == "number" and op in ("exact", "range"):
        values = [_number(v) for v in (_list(raw) if op == "range" else [raw])]
        lookup = {f"{column}__{op}": values if op == "range" else values[0]}
    elif ft in ("date", "datetime") and op in ("exact", "range"):
        values = [_date(v) for v in (_list(raw) if op == "range" else [raw])]
        lookup = {f"{column}__date__{op}": values if op == "range" else values[0]}
    elif ft == "boolean" and op == "exact":
        lookup = {column: _boolean(raw)}
    elif ft in ("select", "multi_select", "member", "multi_member") and op in ("exact", "in"):
        values = [_uuid(v) for v in (_list(raw) if op == "in" else [raw])]
        lookup = {f"{column}__in": values}
    else:
        raise _bad("invalid_filter", f"Operator '{op}' is not supported for {ft}", attribute_id=str(attribute.id))
    if op == "range" and len(lookup[next(iter(lookup))]) != 2:
        raise _bad("invalid_filter", "Range needs two values 'from,to'", attribute_id=str(attribute.id))
    return Q(id__in=AttributeValue.objects.filter(attribute=attribute, **lookup).values("issue_id"))


def _project_attribute(raw_id: str, project_id) -> Attribute:
    attribute = None
    if project_id:
        try:
            attribute = Attribute.objects.filter(id=uuid.UUID(raw_id), project_id=project_id, is_active=True).first()
        except ValueError:
            pass
    if attribute is None:
        raise _bad("invalid_attribute", "Attribute not found in this project", attribute_id=raw_id)
    return attribute


def is_ee_filter_key(key: str) -> bool:
    return key in TYPE_KEYS or key.startswith(PREFIX)


def _type_q(raw: Any) -> Q:
    ids, keys = [], []
    for value in _list(raw):
        try:
            ids.append(uuid.UUID(str(value)))
        except ValueError:
            keys.append(str(value))
    return Q(type_id__in=ids) | Q(type__external_source=AGILE_SOURCE, type__external_id__in=keys)


def split_ee_conditions(conditions: dict, view) -> tuple[Q, dict]:
    """Pull our keys out of a filter leaf; return (Q for them, remaining core conditions)."""
    ee_q, rest = Q(), {}
    for key, raw in conditions.items():
        if key in TYPE_KEYS:
            ee_q &= _type_q(raw)
        elif key.startswith(PREFIX):
            raw_id, _, op = key[len(PREFIX) :].partition("__")
            attribute = _project_attribute(raw_id, view.kwargs.get("project_id"))
            ee_q &= build_attribute_q(attribute, op or "exact", raw)
        else:
            rest[key] = raw
    return ee_q, rest


def resolve_group_by(queryset, group_by, sub_group_by, project_id):
    """Map `type` -> type_id and `attribute:<id>` -> an annotated value column."""

    def resolve(key):
        nonlocal queryset
        if key == "type":
            return "type_id"
        if not key or not key.startswith(PREFIX):
            return key
        attribute = _project_attribute(key[len(PREFIX) :], project_id)
        if attribute.field_type not in GROUPABLE:
            raise _bad(
                "invalid_group_by",
                "Only select, member and boolean attributes can be grouped",
                attribute_id=str(attribute.id),
            )
        name = f"{GROUP_PREFIX}{attribute.id.hex}"
        values = AttributeValue.objects.filter(issue_id=OuterRef("pk"), attribute=attribute)
        queryset = queryset.annotate(**{name: Subquery(values.values(_COLUMN[attribute.field_type])[:1])})
        return name

    group_by, sub_group_by = resolve(group_by), resolve(sub_group_by)
    return queryset, group_by, sub_group_by


def is_ee_group_field(name) -> bool:
    """Strict allowlist for names produced by resolve_group_by (they reach F()/values())."""
    return name == "type_id" or bool(isinstance(name, str) and re.fullmatch(rf"{GROUP_PREFIX}[0-9a-f]{{32}}", name))


def extra_result_fields(*group_keys) -> list[str]:
    return [k for k in group_keys if is_ee_group_field(k)]


def group_values(field: str, project_id) -> list:
    if field == "type_id":
        return list(ProjectIssueType.objects.filter(project_id=project_id).values_list("issue_type_id", flat=True))
    if not field.startswith(GROUP_PREFIX) or not project_id:
        return []
    attribute = Attribute.objects.get(id=uuid.UUID(field[len(GROUP_PREFIX) :]), project_id=project_id)
    if attribute.field_type == "boolean":
        return [True, False, "None"]
    if attribute.field_type == "select":
        return list(attribute.options.filter(is_active=True).values_list("id", flat=True)) + ["None"]
    members = ProjectMember.objects.filter(project_id=project_id, is_active=True).values_list("member_id", flat=True)
    return list(members) + ["None"]
