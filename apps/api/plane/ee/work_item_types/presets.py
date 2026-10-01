# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

SOURCE = "plane-work-item-types"
PROCESSES = ("scrum", "agile")

# key: (name, level, is_epic, icon, color)
# icons: Zap/Bug/ListTree are not in LUCIDE_ICONS_LIST -> Epic/AlertTriangle/List
PRESETS = {
    "epic": ("Epic", 4, True, "Epic", "#8B5CF6"),
    "feature": ("Feature", 3, False, "Layers", "#EC4899"),
    "bug": ("Bug", 2, False, "AlertTriangle", "#EF4444"),
    "task": ("Task", 1, False, "CheckSquare", "#3B82F6"),
    "sub_task": ("Sub-task", 0, False, "List", "#64748B"),
    "product_backlog_item": ("Product Backlog Item", 2, False, "BookOpen", "#10B981"),
    "user_story": ("User Story", 2, False, "BookOpen", "#10B981"),
}
SHARED = ("epic", "feature", "bug", "task", "sub_task")
EXCLUSIVE = {"scrum": "product_backlog_item", "agile": "user_story"}  # also the project default
