import { useState } from "react";
import { runInAction } from "mobx";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { WorkspaceListItem as CoreWorkspaceListItem } from "@/components/workspace/list-item";
import { useWorkspace } from "@/hooks/store";
import { godModeService } from "./service";

/** Core workspace row + Archive all / Delete actions. Swapped in by the workspaces page. */
export const WorkspaceListItem = observer(function WorkspaceListItem({ workspaceId }: { workspaceId: string }) {
  const workspaceStore = useWorkspace();
  const workspace = workspaceStore.getWorkspaceById(workspaceId);
  const [dialog, setDialog] = useState<"delete" | "archive" | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!workspace) return null;

  const close = () => {
    setDialog(null);
    setConfirmText("");
  };

  const run = async (action: () => Promise<string>, failMessage: string) => {
    setIsSubmitting(true);
    try {
      setToast({ type: "success", title: "Success", message: await action() });
      close();
    } catch (error: any) {
      setToast({ type: "error", title: "Error", message: error?.error ?? failMessage });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = () =>
    run(async () => {
      await godModeService.deleteWorkspace(workspace.slug);
      runInAction(() => {
        delete workspaceStore.workspaces[workspaceId];
      });
      return `Workspace "${workspace.name}" deleted.`;
    }, "Failed to delete workspace.");

  const handleArchive = () =>
    run(async () => {
      const { archived_projects } = await godModeService.archiveWorkspaceProjects(workspace.slug);
      return `Archived ${archived_projects} project(s) in "${workspace.name}".`;
    }, "Failed to archive projects.");

  return (
    <div className="flex items-center gap-2">
      <ConfirmDialog
        isOpen={dialog === "delete"}
        handleClose={close}
        handleSubmit={handleDelete}
        isSubmitting={isSubmitting}
        isDisabled={confirmText !== "CONFIRM"}
        variant="danger"
        title="Delete workspace"
        content={
          <div className="flex flex-col gap-3">
            <span>
              Delete <b>{workspace.name}</b> and all its data? Type <b>CONFIRM</b> to continue.
            </span>
            <Input
              size="lg"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="CONFIRM"
              autoComplete="off"
            />
          </div>
        }
        primaryButtonText={{ loading: "Deleting", default: "Delete" }}
      />
      <ConfirmDialog
        isOpen={dialog === "archive"}
        handleClose={close}
        handleSubmit={handleArchive}
        isSubmitting={isSubmitting}
        variant="warning"
        title="Archive all projects"
        content={`Archive every active project in "${workspace.name}"? Members can't work in them until restored.`}
        primaryButtonText={{ loading: "Archiving", default: "Archive all" }}
      />
      <div className="min-w-0 flex-1">
        <CoreWorkspaceListItem workspaceId={workspaceId} />
      </div>
      <Button variant="secondary" size="sm" stretch="auto" label="Archive all" onClick={() => setDialog("archive")} />
      <Button variant="danger" size="sm" stretch="auto" label="Delete" onClick={() => setDialog("delete")} />
    </div>
  );
});
