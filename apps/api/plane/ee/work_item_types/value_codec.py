import datetime as dt
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from plane.db.models import ProjectMember
from plane.ee.models import Attribute, AttributeValue

from .exceptions import WorkItemValidationError

_url_validator = URLValidator(schemes=["http", "https"])
INTEGER_KEYS = {"business_value"}


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _invalid(attribute: Attribute, message: str) -> WorkItemValidationError:
    return WorkItemValidationError("invalid_value", message, {"attribute_id": str(attribute.id)})


def _to_uuid(attribute: Attribute, raw: Any) -> UUID:
    try:
        return raw if isinstance(raw, UUID) else uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        raise _invalid(attribute, "Expected a UUID") from None


def _to_option(attribute: Attribute, raw: Any):
    option_id = _to_uuid(attribute, raw)
    # in memory: write_values prefetches options, so N option values cost no extra queries
    option = next((o for o in attribute.options.all() if o.id == option_id and o.is_active), None)
    if option is None:
        raise _invalid(attribute, "Option does not belong to this attribute")
    return option


def _to_number(attribute: Attribute, raw: Any) -> Decimal:
    if isinstance(raw, bool):
        raise _invalid(attribute, "Expected a number")
    try:
        num = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        raise _invalid(attribute, "Expected a number") from None
    if not num.is_finite():
        raise _invalid(attribute, "Expected a number")
    if num < 0:
        raise _invalid(attribute, "Number must be >= 0")
    _, digits, exp = num.as_tuple()
    frac = max(-exp, 0)
    if frac > 4 or len(digits) + max(exp, 0) - frac > 16:
        raise _invalid(attribute, "Number out of range (max 16 integer and 4 decimal digits)")
    if attribute.system_key in INTEGER_KEYS and num != num.to_integral_value():
        raise _invalid(attribute, "Expected an integer")
    return num


def _to_datetime(attribute: Attribute, raw: Any, date_only: bool) -> dt.datetime:
    value = raw
    if isinstance(raw, str):
        try:
            value = parse_date(raw) if date_only else (parse_datetime(raw) or parse_date(raw))
        except ValueError:
            raise _invalid(attribute, "Expected a valid date") from None
    if isinstance(value, dt.datetime):
        pass
    elif isinstance(value, dt.date):
        value = dt.datetime.combine(value, dt.time.min)
    else:
        raise _invalid(attribute, "Expected a date")
    return timezone.make_aware(value, dt.timezone.utc) if timezone.is_naive(value) else value


def _many(attribute: Attribute, raw: Any, one) -> list:
    if not isinstance(raw, (list, tuple)):
        raise _invalid(attribute, "Expected a list")
    return [one(attribute, item) for item in raw]


def is_empty(raw: Any) -> bool:
    return raw is None or raw == "" or raw == [] or raw == ()


def coerce_value(attribute: Attribute, raw: Any) -> dict[str, Any]:
    """Return {typed_column: value}. Multi types return lists (one row each). Empty raw -> {}."""
    if is_empty(raw):
        return {}
    ft = attribute.field_type
    if ft in ("text", "textarea"):
        if not isinstance(raw, str):
            raise _invalid(attribute, "Expected a string")
        return {"value_text": raw}
    if ft == "url":
        try:
            _url_validator(raw)
        except (DjangoValidationError, TypeError):
            raise _invalid(attribute, "Expected a valid URL") from None
        return {"value_text": raw}
    if ft == "number":
        return {"value_number": _to_number(attribute, raw)}
    if ft == "boolean":
        if not isinstance(raw, bool):
            raise _invalid(attribute, "Expected a boolean")
        return {"value_boolean": raw}
    if ft in ("date", "datetime"):
        return {"value_datetime": _to_datetime(attribute, raw, ft == "date")}
    if ft == "select":
        return {"value_option": _to_option(attribute, raw)}
    if ft == "multi_select":
        return {"value_option": _many(attribute, raw, _to_option)}
    if ft == "member":
        return {"value_uuid": _to_uuid(attribute, raw)}
    if ft == "multi_member":
        return {"value_uuid": _many(attribute, raw, _to_uuid)}
    raise _invalid(attribute, f"Unsupported field type {ft}")


def write_values(issue, values: dict[UUID, Any], *, project) -> None:
    keys = {}
    for k in values:
        try:
            keys[k] = _as_uuid(k)
        except (ValueError, AttributeError, TypeError):
            raise WorkItemValidationError("invalid_value", "Malformed attribute id", {"attribute_id": str(k)}) from None
    attrs = {
        a.id: a
        for a in Attribute.objects.filter(
            id__in=list(keys.values()), project=project, issue_type_id=issue.type_id, is_active=True
        ).prefetch_related("options")
    }
    coerced = []
    for k, raw in values.items():
        attribute = attrs.get(keys[k])
        if attribute is None:
            raise WorkItemValidationError("invalid_value", "Unknown attribute for this type", {"attribute_id": str(k)})
        cols = coerce_value(attribute, raw)
        if attribute.field_type in ("member", "multi_member") and cols:
            ids = set(cols["value_uuid"] if isinstance(cols["value_uuid"], list) else [cols["value_uuid"]])
            members = ProjectMember.objects.filter(project=project, member_id__in=ids, is_active=True).count()
            if members != len(ids):
                raise _invalid(attribute, "Member is not part of this project")
        coerced.append((attribute, cols))
    if not coerced:
        return
    rows = []
    for attribute, cols in coerced:
        if not cols:
            continue
        ((col, val),) = cols.items()
        rows += [
            AttributeValue(
                issue=issue, attribute=attribute, project=project, workspace_id=project.workspace_id, **{col: item}
            )
            for item in (val if isinstance(val, list) else [val])
        ]
    with transaction.atomic():
        # serialise concurrent writers on this issue so a single-valued attribute never ends up with two rows
        type(issue).all_objects.select_for_update().filter(pk=issue.pk).values_list("pk", flat=True).first()
        # delete + rewrite handles single and multi_* uniformly; hard delete so rewrites leave no dead rows
        AttributeValue.objects.filter(issue=issue, attribute__in=[a for a, _ in coerced]).delete(soft=False)
        AttributeValue.objects.bulk_create(rows)


def missing_required(project_id: UUID, issue_type_id: UUID, values: dict[UUID, Any]) -> list[UUID]:
    provided = {}
    for k, v in values.items():
        try:
            provided[_as_uuid(k)] = v
        except (ValueError, AttributeError, TypeError):
            continue  # malformed ids are rejected by write_values
    required = Attribute.objects.filter(
        project_id=project_id, issue_type_id=issue_type_id, is_required=True, is_active=True
    ).values_list("id", flat=True)
    return [a for a in required if is_empty(provided.get(a))]
