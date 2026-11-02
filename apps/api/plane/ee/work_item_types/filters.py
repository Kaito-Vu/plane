"""Filter / group-by by issue type and attribute (spec §8). Core seams call in here only
when a key is ours, so requests without `type` / `attribute:<id>` keys pay nothing.

Lookups go through the typed AttributeValue columns, served by the
(attribute, value_*) indexes in plane.ee.models.value (no JSON scan)."""

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import OuterRef, Q, Subquery, UUIDField
from django.db.models.functions import Cast
from django.utils.dateparse import parse_date

from plane.db.models import ProjectMember
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.models import Attribute, AttributeValue

from .constants import AGILE_SOURCE
from .exceptions import WorkItemValidationError

PREFIX = "attribute:"
GROUP_PREFIX = "attr_"
TYPE_GROUP = "ee_type"
_GROUP_NAME = re.compile(r"attr_[0-9a-f]{32}")
TYPE_KEYS = {"type", "type__in", "type__isnull"}
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
        value = Decimal(str(raw))
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite():  # NaN/Infinity: not comparable in a filter
        raise _bad("invalid_filter", "Expected a number", value=str(raw))
    return value


def _date(raw: Any):
    try:
        value = parse_date(str(raw))
    except ValueError:  # well-formed but not a calendar date, e.g. 2026-02-30
        value = None
    if value is None:
        raise _bad("invalid_filter", "Expected a date (YYYY-MM-DD)", value=str(raw))
    return value


def _boolean(raw: Any) -> bool:
    text = str(raw).lower()
    if text not in ("true", "false"):
        raise _bad("invalid_filter", "Expected true or false", value=str(raw))
    return text == "true"


def _range(attribute: Attribute, raw: Any, parse) -> list:
    values = [parse(v) for v in _list(raw)]
    if len(values) != 2:
        raise _bad("invalid_filter", "Range needs two values 'from,to'", attribute_id=str(attribute.id))
    return values


def build_attribute_q(attribute: Attribute, op: str, raw: Any) -> Q:
    """Q on Issue: issues whose value for `attribute` matches `op`/`raw`."""
    ft = attribute.field_type
    column = _COLUMN[ft]
    if ft in ("text", "textarea", "url") and op in ("contains", "icontains"):
        lookup = {f"{column}__icontains": str(raw)}
    elif ft == "number" and op in ("exact", "gte", "lte"):
        lookup = {column if op == "exact" else f"{column}__{op}": _number(raw)}
    elif ft == "number" and op == "range":
        lookup = {f"{column}__range": _range(attribute, raw, _number)}
    elif ft in ("date", "datetime") and op in ("exact", "gte", "lte"):
        lookup = {f"{column}__date" if op == "exact" else f"{column}__date__{op}": _date(raw)}
    elif ft in ("date", "datetime") and op == "range":
        lookup = {f"{column}__date__range": _range(attribute, raw, _date)}
    elif ft == "boolean" and op in ("exact", "in"):
        lookup = {f"{column}__in": [_boolean(v) for v in (_list(raw) if op == "in" else [raw])]}
    elif ft in ("select", "multi_select", "member", "multi_member") and op in ("exact", "in"):
        lookup = {f"{column}__in": [_uuid(v) for v in (_list(raw) if op == "in" else [raw])]}
    else:
        raise _bad("invalid_filter", f"Operator '{op}' is not supported for {ft}", attribute_id=str(attribute.id))
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


def _isnull_q(attribute: Attribute, raw: Any) -> Q:
    """No value for `attribute` (the group-by "None" bucket) when raw is true, any value otherwise."""
    has = Q(
        id__in=AttributeValue.objects.filter(
            attribute=attribute, **{f"{_COLUMN[attribute.field_type]}__isnull": False}
        ).values("issue_id")
    )
    return ~has if _boolean(raw) else has


def split_ee_conditions(conditions: dict, view) -> tuple[Q, dict]:
    """Pull our keys out of a filter leaf; return (Q for them, remaining core conditions)."""
    ee_q, rest = Q(), {}
    for key, raw in conditions.items():
        if key == "type__isnull":
            ee_q &= Q(type__isnull=_boolean(raw))
        elif key in TYPE_KEYS:
            ee_q &= _type_q(raw)
        elif key.startswith(PREFIX):
            raw_id, _, op = key[len(PREFIX) :].partition("__")
            attribute = _project_attribute(raw_id, view.kwargs.get("project_id"))
            ee_q &= _isnull_q(attribute, raw) if op == "isnull" else build_attribute_q(attribute, op or "exact", raw)
        else:
            rest[key] = raw
    return ee_q, rest


def resolve_group_by(queryset, group_by, sub_group_by, project_id):
    """Map `type` / `attribute:<id>` to an annotation on the queryset. Only names that are
    real annotations pass is_ee_group_field, so hand-crafted `attr_*`/`ee_type` get a 400."""

    def resolve(key):
        nonlocal queryset
        if key == "type":
            # Cast: a bare F("type_id") alias collides with type_id in values() (Django dedupes the column)
            queryset = queryset.annotate(**{TYPE_GROUP: Cast("type_id", UUIDField())})
            return TYPE_GROUP
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


def _is_ee_name(name) -> bool:
    return isinstance(name, str) and (name == TYPE_GROUP or bool(_GROUP_NAME.fullmatch(name)))


def is_ee_group_field(name, queryset) -> bool:
    """Paginator allowlist hook: an EE name is valid only if resolve_group_by annotated it."""
    return _is_ee_name(name) and queryset is not None and name in queryset.query.annotations


def extra_result_fields(*group_keys) -> list[str]:
    return [k for k in group_keys if _is_ee_name(k)]


def group_values(field: str, project_id) -> list:
    if not project_id or not _is_ee_name(field):
        return []
    if field == TYPE_GROUP:
        types = ProjectIssueType.objects.filter(project_id=project_id).values_list("issue_type_id", flat=True)
        return list(types) + ["None"]  # untyped (pre-migration) issues
    attribute = Attribute.objects.filter(id=uuid.UUID(field[len(GROUP_PREFIX) :]), project_id=project_id).first()
    if attribute is None:
        return []
    if attribute.field_type == "boolean":
        return [True, False, "None"]
    if attribute.field_type == "select":
        return list(attribute.options.filter(is_active=True).values_list("id", flat=True)) + ["None"]
    members = ProjectMember.objects.filter(project_id=project_id, is_active=True).values_list("member_id", flat=True)
    return list(members) + ["None"]
