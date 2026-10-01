# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

from django.conf import settings
from rest_framework import serializers

from plane.db.models import IssueType
from plane.ee.work_item_types.contrast import contrast_ratio

ICON_NAME = re.compile(r"^[A-Za-z0-9]{1,64}$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_logo_props(value):
    """Shape validation only. Icon names are deliberately NOT whitelisted: the frontend renders only names it
    knows and ignores the rest, so an unknown name is harmless."""
    if value in (None, {}):
        return {}
    if not isinstance(value, dict) or set(value) - {"in_use", "icon", "emoji"}:
        raise serializers.ValidationError("Invalid logo_props")
    if value.get("in_use") not in ("icon", "emoji", None):
        raise serializers.ValidationError("Invalid logo_props")
    icon = value.get("icon")
    if icon is not None:
        if not isinstance(icon, dict) or set(icon) - {"name", "color", "background_color"}:
            raise serializers.ValidationError("Invalid icon")
        if "name" in icon and not (isinstance(icon["name"], str) and ICON_NAME.match(icon["name"])):
            raise serializers.ValidationError("Invalid icon name")
        for key in ("color", "background_color"):
            if key in icon and not (isinstance(icon[key], str) and HEX.match(icon[key])):
                raise serializers.ValidationError(f"Invalid {key}")
    emoji = value.get("emoji")
    if emoji is not None:
        if not isinstance(emoji, dict) or set(emoji) - {"value", "url"}:
            raise serializers.ValidationError("Invalid emoji")
        if any(not isinstance(v, str) or len(v) > 512 for v in emoji.values()):
            raise serializers.ValidationError("Invalid emoji")
    return value


class IssueTypeSerializer(serializers.ModelSerializer):
    level = serializers.IntegerField(min_value=0, max_value=9)
    is_preset = serializers.SerializerMethodField()
    low_contrast = serializers.SerializerMethodField()

    class Meta:
        model = IssueType
        fields = ["id", "name", "description", "logo_props", "is_epic", "is_default", "is_active", "level", "is_preset", "low_contrast"]
        read_only_fields = ["id", "is_default", "is_preset", "low_contrast"]

    def get_is_preset(self, obj):
        return obj.external_source == "plane-work-item-types"

    def get_low_contrast(self, obj):
        icon = (obj.logo_props or {}).get("icon") or {}
        fg, bg = icon.get("color"), icon.get("background_color")
        return bool(fg and bg and contrast_ratio(fg, bg) < 4.5)  # warning only, never rejected

    def validate_logo_props(self, value):
        return validate_logo_props(value)

    def validate_name(self, value):
        value = value.strip()
        qs = IssueType.objects.filter(workspace=self.context["workspace"], name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A work item type with this name already exists")
        return value

    def validate(self, attrs):
        if not self.instance:
            cap = getattr(settings, "WORK_ITEM_TYPES_MAX", 50)
            if IssueType.objects.filter(workspace=self.context["workspace"]).count() >= cap:
                raise serializers.ValidationError(f"At most {cap} work item types are allowed")
        return attrs
