import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import { TYPE_COLORS } from "../constants";
import { useAttributes, useEnsureProjectTypes } from "../hooks/use-attributes";
import type { TWorkItemTypeKey } from "../types";

type TTypeKeyBadgeProps = { typeKey: TWorkItemTypeKey; compact?: boolean; className?: string };

/** Coloured pill for a type key. `compact` shows only the first letter (dense rows). */
export function TypeKeyBadge({ typeKey, compact = false, className }: TTypeKeyBadgeProps) {
  const { t } = useTranslation();
  const label = t(`agile_attributes.types.${typeKey}`);
  const color = TYPE_COLORS[typeKey];
  return (
    <span
      title={label}
      className={cn(
        "inline-flex shrink-0 items-center rounded-sm px-1 text-11 leading-4 font-medium whitespace-nowrap",
        className
      )}
      style={{ color, backgroundColor: `${color}1a`, border: `1px solid ${color}40` }}
    >
      {compact ? label.charAt(0) : label}
    </span>
  );
}

type TTypeBadgeProps = { projectId: string | null | undefined; typeId: string | null | undefined } & Omit<
  TTypeKeyBadgeProps,
  "typeKey"
>;

/** Badge for an issue's type_id; renders nothing until the project's types are loaded. */
export const TypeBadge = observer(function TypeBadge({ projectId, typeId, ...rest }: TTypeBadgeProps) {
  const { workspaceSlug } = useParams();
  const { getTypeKey } = useAttributes();
  useEnsureProjectTypes(workspaceSlug?.toString(), projectId);
  const key = getTypeKey(projectId, typeId);
  return key ? <TypeKeyBadge typeKey={key} {...rest} /> : null;
});
