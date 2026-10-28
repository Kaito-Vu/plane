from rest_framework import serializers

from plane.ee.models import Attribute, AttributeOption, AttributeTemplate, AttributeTemplateOption

OPTION_FIELDS = ["id", "name", "sort_order", "is_active", "color", "is_default"]


class AttributeTemplateOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeTemplateOption
        fields = OPTION_FIELDS


class AttributeOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeOption
        fields = OPTION_FIELDS


class AttributeTemplateSerializer(serializers.ModelSerializer):
    options = AttributeTemplateOptionSerializer(many=True, read_only=True)

    class Meta:
        model = AttributeTemplate
        fields = [
            "id", "issue_type", "name", "description", "field_type", "is_required",
            "default_value", "settings", "sort_order", "is_active", "options",
        ]  # fmt: skip


class AttributeSerializer(serializers.ModelSerializer):
    options = AttributeOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Attribute
        fields = [
            "id", "issue_type", "name", "description", "field_type", "is_required", "is_system",
            "source_template", "system_key", "default_value", "settings", "sort_order", "is_active", "options",
        ]  # fmt: skip
        read_only_fields = ["is_system", "source_template", "system_key"]
