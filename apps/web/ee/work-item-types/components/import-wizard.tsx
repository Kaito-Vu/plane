import { useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { setToast } from "@plane/blocks/toast";
import { TYPE_KEYS } from "../constants";
import { useAttributes } from "../hooks/use-attributes";
import { csvToImportRows, parseCsv } from "../import-csv";
import { AttributeService } from "../services/attribute.service";
import type { TImportRow, TImportRowError, TWorkItemTypeKey } from "../types";
import { asEeError } from "../work-item-errors";
import { BorderedInput as Input } from "./attribute-form/bordered-input";
import { ParentPicker } from "./parent-picker";

const service = new AttributeService();

type Props = { isOpen: boolean; onClose: () => void; workspaceSlug: string; projectId: string };

const withErrors = (rows: TImportRow[], errors: TImportRowError[]) =>
  rows.map((r) => ({ ...r, errors: errors.filter((e) => e.ref === r.ref) }));

/** Two-step import: 1) upload CSV into a staging batch, 2) fix parents/errors, dry-run, commit. */
export const ImportWizard = observer(function ImportWizard({ isOpen, onClose, workspaceSlug, projectId }: Props) {
  const { getProjectAttributes, getTypeId } = useAttributes();
  const [batchId, setBatchId] = useState<string>();
  const [rows, setRows] = useState<TImportRow[]>([]);
  const [valid, setValid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [batchError, setBatchError] = useState<string>();

  const close = () => {
    setBatchId(undefined);
    setRows([]);
    setValid(false);
    setBatchError(undefined);
    onClose();
  };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setBatchError(undefined);
    try {
      await fn();
    } catch (err) {
      const e = asEeError(err);
      const rowErrors = (e?.details as { errors?: TImportRowError[] } | undefined)?.errors;
      if (rowErrors) setRows((prev) => withErrors(prev, rowErrors));
      setBatchError(e?.message ?? "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const dryRun = (id = batchId) =>
    run(async () => {
      if (!id) return;
      const res = await service.validateImport(workspaceSlug, projectId, id);
      setRows((prev) => withErrors(prev, res.errors));
      setValid(res.valid);
    });

  const upload = (file: File) =>
    run(async () => {
      const payload = csvToImportRows(parseCsv(await file.text()), getProjectAttributes(projectId), (key) =>
        TYPE_KEYS.includes(key as TWorkItemTypeKey) ? getTypeId(projectId, key as TWorkItemTypeKey) : undefined
      );
      if (payload.length === 0) throw { error_code: "empty_batch", message: "The CSV has no data rows" };
      const batch = await service.createImportBatch(workspaceSlug, projectId);
      setRows(await service.addImportRows(workspaceSlug, projectId, batch.id, payload));
      setBatchId(batch.id);
      const res = await service.validateImport(workspaceSlug, projectId, batch.id);
      setRows((prev) => withErrors(prev, res.errors));
      setValid(res.valid);
    });

  const patchRow = (row: TImportRow, data: Record<string, unknown>) =>
    run(async () => {
      if (!batchId) return;
      const updated = await service.updateImportRow(workspaceSlug, projectId, batchId, row.id, data);
      setRows((prev) => prev.map((r) => (r.id === row.id ? updated : r)));
      setValid(false); // edits need a fresh dry-run
    });

  const commit = () =>
    run(async () => {
      if (!batchId) return;
      const res = await service.commitImport(workspaceSlug, projectId, batchId);
      setToast({
        type: "success",
        title: "Import complete",
        message: `${Object.keys(res.created).length} work items created`,
      });
      close();
    });

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
      <DialogContent size="xl">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>{batchId ? "Import: review rows" : "Import: upload CSV"}</DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            <div className="flex flex-col gap-3 text-13">
              {!batchId ? (
                <>
                  <p className="text-secondary">
                    Columns: <code>ref, type, parent_ref, parent_id, name</code>; any column named like an attribute of
                    the row&apos;s type fills that attribute (multi values separated by &quot;;&quot;). Other columns
                    (e.g. <code>priority</code>) go to the work item as-is.
                  </p>
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    disabled={busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void upload(file);
                    }}
                  />
                </>
              ) : (
                <div className="max-h-[60vh] overflow-auto">
                  <table className="w-full text-left text-12">
                    <thead>
                      <tr className="text-tertiary">
                        <th className="p-1">Ref</th>
                        <th className="p-1">Type</th>
                        <th className="p-1">Name</th>
                        <th className="p-1">Parent ref (in file)</th>
                        <th className="p-1">Existing parent</th>
                        <th className="p-1">Errors</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <ImportRowView key={row.id} row={row} {...{ workspaceSlug, projectId, busy, patchRow }} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {batchError && <p className="text-danger-primary">{batchError}</p>}
              {batchId && valid && <p className="text-success-primary">Dry-run passed: ready to commit.</p>}
            </div>
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button stretch="auto" variant="secondary" size="md" label="Cancel" onClick={close} />
          {batchId && (
            <>
              <Button
                stretch="auto"
                variant="secondary"
                size="md"
                disabled={busy}
                label="Dry-run"
                onClick={() => void dryRun()}
              />
              <Button
                stretch="auto"
                variant="primary"
                size="md"
                disabled={busy || !valid}
                label="Commit"
                onClick={() => void commit()}
              />
            </>
          )}
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
});

function ImportRowView(props: {
  row: TImportRow;
  workspaceSlug: string;
  projectId: string;
  busy: boolean;
  patchRow: (row: TImportRow, data: Record<string, unknown>) => Promise<void>;
}) {
  const { row, workspaceSlug, projectId, busy, patchRow } = props;
  const typeKey = TYPE_KEYS.includes(row.type as TWorkItemTypeKey) ? (row.type as TWorkItemTypeKey) : undefined;
  const commitText = (field: "name" | "parent_ref", value: string) => {
    if (value === (row[field] ?? "")) return;
    void patchRow(row, field === "parent_ref" && !value ? { parent_ref: null } : { [field]: value });
  };
  return (
    <tr className={row.errors.length ? "bg-danger-subtle" : undefined}>
      <td className="p-1">{row.ref}</td>
      <td className="p-1">{row.type}</td>
      <td className="p-1">
        <Input
          size="md"
          defaultValue={row.name}
          disabled={busy}
          onBlur={(e: React.FocusEvent<HTMLInputElement>) => commitText("name", e.target.value)}
        />
      </td>
      <td className="p-1">
        <Input
          size="md"
          defaultValue={row.parent_ref ?? ""}
          disabled={busy}
          onBlur={(e: React.FocusEvent<HTMLInputElement>) => commitText("parent_ref", e.target.value)}
        />
      </td>
      <td className="p-1">
        {typeKey ? (
          <ParentPicker
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            typeKey={typeKey}
            value={null}
            disabled={busy}
            onChange={(issue) => issue && void patchRow(row, { parent_id: issue.id })}
          />
        ) : null}
        {row.parent_id && <span className="text-tertiary">{row.parent_id.slice(0, 8)}</span>}
      </td>
      <td className="p-1 text-danger-primary">{row.errors.map((e) => e.message).join("; ")}</td>
    </tr>
  );
}
