from enum import Enum


class TypeKey(str, Enum):
    EPIC = "epic"
    FEATURE = "feature"
    USER_STORY = "user_story"
    TASK = "task"
    BUG = "bug"
    SUB_TASK = "sub_task"


T = TypeKey
AGILE_SOURCE = "agile"
MAX_DEPTH = 10

PARENT_RULES: dict[TypeKey, frozenset[TypeKey]] = {
    T.EPIC: frozenset({T.EPIC}),
    T.FEATURE: frozenset({T.EPIC, T.FEATURE}),
    T.USER_STORY: frozenset({T.FEATURE}),
    T.TASK: frozenset({T.USER_STORY}),
    T.BUG: frozenset({T.TASK, T.USER_STORY}),
    T.SUB_TASK: frozenset({T.TASK, T.BUG}),
}

# Types that may be assigned to a sprint (spec §3)
SPRINT_TYPES: frozenset[TypeKey] = frozenset({T.USER_STORY, T.TASK, T.BUG, T.SUB_TASK})
