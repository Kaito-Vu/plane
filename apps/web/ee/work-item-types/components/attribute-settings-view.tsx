import { useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { draggable, dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { LockOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";
import type { TWorkItemTypeKey } from "../types";
import { AttributeFormModal } from "./attribute-form/attribute-form-modal";
import { runWithToast } from "./attribute-form/helpers";
import type { TAttributeApi, TAttributeLike } from "./attribute-form/helpers";

type RowProps = {
  item: TAttributeLike;
  canEdit: boolean;
  onMove: (sourceId: string, targetId: string) => void;
  onEdit: () => void;
  onToggleActive: () => void;
  onDelete: () => void;
};

function AttributeRow({ item, canEdit, onMove, onEdit, onToggleActive, onDelete }: RowProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const [isOver, setIsOver] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element || !canEdit) return;
    return combine(
      draggable({ element, getInitialData: () => ({ attributeId: item.id }) }),
      dropTargetForElements({
        element,
        canDrop: ({ source }) => source.data.attributeId !== item.id,
        onDragEnter: () => setIsOver(true),
        onDragLeave: () => setIsOver(false),
        onDrop: ({ source }) => {
          setIsOver(false);
          onMove(String(source.data.attributeId), item.id);
        },
      })
    );
  }, [item.id, canEdit, onMove]);

  return (
    <div
      ref={ref}
      className={cn(
        "flex items-center gap-3 rounded-md border border-subtle bg-surface-1 px-3 py-2",
        canEdit && "cursor-grab",
        isOver && "border-accent-strong",
        !item.is_active && "opacity-60"
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {item.is_system && <LockOutline className="size-3.5 shrink-0 text-tertiary" />}
        <span className="truncate text-13 font-medium">{item.name}</span>
        <span className="text-12 text-tertiary">{t(`agile_attributes.field_types.${item.field_type}`)}</span>
        {item.is_system && <Badge variant="neutral" size="xs" label={t("agile_attributes.badges.system")} />}
        {item.is_required && <Badge variant="brand" size="xs" label={t("agile_attributes.badges.required")} />}
        {!item.is_active && <Badge variant="neutral" size="xs" label={t("agile_attributes.badges.hidden")} />}
      </div>
      {canEdit && (
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" label={t("agile_attributes.actions.edit")} onClick={onEdit} />
          {!item.is_system && (
            <>
              <Button
                variant="ghost"
                size="sm"
                label={t(item.is_active ? "agile_attributes.actions.hide" : "agile_attributes.actions.show")}
                onClick={onToggleActive}
              />
              <Button variant="ghost" size="sm" label={t("agile_attributes.actions.delete")} onClick={onDelete} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

type Props = {
  typeIds: Partial<Record<TWorkItemTypeKey, string>>;
  typeKey: TWorkItemTypeKey;
  onTypeChange: (key: TWorkItemTypeKey) => void;
  /** all items (any type, active or hidden) */
  items: TAttributeLike[];
  api: TAttributeApi;
  reload: () => Promise<unknown>;
  canEdit: boolean;
  extraActions?: React.ReactNode;
};

const TYPE_KEYS: TWorkItemTypeKey[] = ["epic", "feature", "user_story", "task", "bug", "sub_task"];

export function AttributeSettingsView(props: Props) {
  const { typeIds, typeKey, onTypeChange, items, api, reload, canEdit, extraActions } = props;
  const { t } = useTranslation();
  const [editing, setEditing] = useState<{ id: string | undefined } | undefined>();
  const typeId = typeIds[typeKey];
  const list = items.filter((a) => a.issue_type === typeId).toSorted((a, b) => a.sort_order - b.sort_order);
  const editingItem = editing?.id ? items.find((a) => a.id === editing.id) : undefined;

  const run = async (fn: () => Promise<unknown>) => {
    await runWithToast(t, fn);
    await reload();
  };

  const move = (sourceId: string, targetId: string) => {
    if (!typeId) return;
    const ids = list.map((a) => a.id).filter((id) => id !== sourceId);
    ids.splice(ids.indexOf(targetId), 0, sourceId);
    void run(() => api.reorder(ids, typeId));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label={t("agile_attributes.type_select")}
          className="rounded-md border border-subtle bg-surface-1 px-2 py-1.5 text-13"
          value={typeKey}
          onChange={(e) => onTypeChange(e.target.value as TWorkItemTypeKey)}
        >
          {TYPE_KEYS.filter((k) => typeIds[k]).map((k) => (
            <option key={k} value={k}>
              {t(`agile_attributes.types.${k}`)}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        {canEdit && extraActions}
        {canEdit && typeId && (
          <Button
            variant="primary"
            size="md"
            label={t("agile_attributes.actions.add")}
            onClick={() => setEditing({ id: undefined })}
          />
        )}
      </div>
      {list.length === 0 ? (
        <p className="text-13 text-tertiary">{t("agile_attributes.empty")}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {list.map((a) => (
            <AttributeRow
              key={a.id}
              item={a}
              canEdit={canEdit}
              onMove={move}
              onEdit={() => setEditing({ id: a.id })}
              onToggleActive={() => void run(() => api.update(a.id, { is_active: !a.is_active }))}
              onDelete={() => {
                // ponytail: native confirm; swap for a Plane dialog if design asks
                if (window.confirm(t("agile_attributes.delete_confirm", { name: a.name })))
                  void run(() => api.remove(a.id));
              }}
            />
          ))}
        </div>
      )}
      {typeId && (
        <AttributeFormModal
          isOpen={!!editing}
          onClose={() => setEditing(undefined)}
          issueTypeId={typeId}
          attribute={editingItem}
          api={api}
          onChanged={reload}
        />
      )}
    </div>
  );
}
