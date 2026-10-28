import itertools

import pytest

from plane.db.models import Issue, IssueType
from plane.ee.work_item_types.constants import MAX_DEPTH, PARENT_RULES, TypeKey
from plane.ee.work_item_types.exceptions import WorkItemValidationError
from plane.ee.work_item_types.hierarchy import assert_no_cycle, depth_of, validate_parent
from plane.ee.work_item_types.registry import get_type, type_key_of

T = TypeKey


@pytest.mark.unit
@pytest.mark.parametrize("t,p", list(itertools.product(TypeKey, TypeKey)))
def test_parent_matrix(t, p):
    if p in PARENT_RULES[t]:
        validate_parent(t, p)
    else:
        with pytest.raises(WorkItemValidationError) as e:
            validate_parent(t, p)
        assert e.value.error_code == "parent_type_invalid"


@pytest.mark.unit
def test_rules_table():
    assert PARENT_RULES[T.EPIC] == {T.EPIC}
    assert PARENT_RULES[T.FEATURE] == {T.EPIC, T.FEATURE}
    assert PARENT_RULES[T.USER_STORY] == {T.FEATURE}
    assert PARENT_RULES[T.TASK] == {T.USER_STORY}
    assert PARENT_RULES[T.BUG] == {T.TASK, T.USER_STORY}
    assert PARENT_RULES[T.SUB_TASK] == {T.TASK, T.BUG}


@pytest.mark.unit
def test_parent_required_except_epic():
    validate_parent(T.EPIC, None)
    with pytest.raises(WorkItemValidationError) as e:
        validate_parent(T.TASK, None)
    assert e.value.error_code == "parent_required"
    assert e.value.detail["error_code"] == "parent_required"


@pytest.mark.unit
def test_triage_skips_parent_required():
    validate_parent(T.TASK, None, triage=True)


@pytest.mark.unit
def test_cycle_rejected():
    a = Issue(name="A")
    b = Issue(name="B", parent=a)
    with pytest.raises(WorkItemValidationError) as e:
        assert_no_cycle(a.id, b)
    assert e.value.error_code == "parent_cycle"
    assert_no_cycle(None, b)


@pytest.mark.unit
def test_depth_over_10_rejected():
    node = Issue(name="0")
    for i in range(MAX_DEPTH - 1):
        node = Issue(name=str(i + 1), parent=node)
    assert depth_of(node) == MAX_DEPTH
    assert_no_cycle(None, None)
    with pytest.raises(WorkItemValidationError) as e:
        assert_no_cycle(None, node)
    assert e.value.error_code == "max_depth_exceeded"


@pytest.mark.unit
@pytest.mark.django_db
def test_registry(workspace):
    assert type_key_of(None) is None
    assert type_key_of(IssueType(external_source="x", external_id="task")) is None
    it = IssueType.objects.create(workspace=workspace, name="Task", external_source="agile", external_id="task")
    assert type_key_of(it) == T.TASK
    assert get_type(workspace.id, T.TASK) == it


@pytest.mark.unit
def test_depth_exactly_10_allowed():
    node = Issue(name="0")
    for i in range(MAX_DEPTH - 2):
        node = Issue(name=str(i + 1), parent=node)
    assert depth_of(node) == MAX_DEPTH - 1
    assert_no_cycle(None, node)


@pytest.mark.unit
def test_unknown_agile_external_id_is_none():
    assert type_key_of(IssueType(external_source="agile", external_id="nope")) is None
