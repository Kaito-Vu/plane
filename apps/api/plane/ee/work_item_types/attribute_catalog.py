from typing import NamedTuple

from .constants import TypeKey

T = TypeKey


class SystemAttrSpec(NamedTuple):
    system_key: str
    name: str
    field_type: str
    is_required: bool = False
    options: tuple[str, ...] = ()


_AC = lambda req=False: SystemAttrSpec("acceptance_criteria", "Acceptance Criteria", "textarea", req)  # noqa: E731
_PHASE = SystemAttrSpec(
    "project_phase", "Project Phase", "select", False, ("Initiation", "Planning", "Execution", "Closing")
)
_AREA = SystemAttrSpec("value_area", "Value Area", "select", False, ("Business", "Architectural"))
_SP = SystemAttrSpec("story_points", "Story Points", "number")
_HOURS = [
    SystemAttrSpec("original_estimate", "Original Estimate", "number"),
    SystemAttrSpec("remaining_work", "Remaining Work", "number"),
    SystemAttrSpec("spent_time", "Spent Time", "number"),
]


def _big(ac_required: bool) -> list[SystemAttrSpec]:
    return [
        _AC(ac_required),
        _SP,
        SystemAttrSpec("business_value", "Business Value", "number"),
        SystemAttrSpec("time_criticality", "Time Criticality", "number"),
        _AREA,
        _PHASE,
    ]


ATTRIBUTE_CATALOG: dict[TypeKey, list[SystemAttrSpec]] = {
    T.EPIC: _big(False),
    T.FEATURE: _big(False),
    T.USER_STORY: _big(True),
    T.TASK: [_AC(), *_HOURS],
    T.SUB_TASK: list(_HOURS),
    T.BUG: [
        SystemAttrSpec("severity", "Severity", "select", True, ("Critical", "Major", "Minor", "Trivial")),
        SystemAttrSpec("steps_to_reproduce", "Steps to Reproduce", "textarea", True),
        SystemAttrSpec("expected_result", "Expected Result", "textarea"),
        SystemAttrSpec("actual_result", "Actual Result", "textarea", True),
        SystemAttrSpec("system_info", "System Info", "textarea"),
        SystemAttrSpec("version_found", "Version Found", "text"),
        _SP,
    ],
}
