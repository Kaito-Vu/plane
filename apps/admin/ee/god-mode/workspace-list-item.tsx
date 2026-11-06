import { useEffect, useState } from "react";
import { runInAction } from "mobx";
import { observer } from "mobx-react";
import { Button } from "@makeplane/propel/components/button";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Input } from "@makeplane/propel/components/input";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@makeplane/propel/components/menu";
import { MoreVerticalOutline } from "@makeplane/propel/icons";
import { ConfirmDialog } from "@plane/blocks/dialog";
import { setToast } from "@plane/blocks/toast";
import { WorkspaceListItem as CoreWorkspaceListItem } from "@/components/workspace/list-item";
import { useWorkspace } from "@/hooks/store";
import { godModeService } from "./service";

const ROLE_LABELS: Record<number, string> = { 20: "Admin", 15: "Member", 5: "Guest" };
type TMember = Awaited<ReturnType<typeof godModeService.searchWorkspaceUsers>>[number];

/** Core workspace row + Archive all / Delete actions. Swapped in by the workspaces page. */
export const WorkspaceListItem = observer(function WorkspaceListItem({ workspaceId }: { workspaceId: string }) {
  const workspaceStore = useWorkspace();
  const workspace = workspaceStore.getWorkspaceById(workspaceId);
  const [dialog, setDialog] = useState<"delete" | "archive" | "assign" | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(15);
  const [selectedEmail, setSelectedEmail] = useState("");
  const [results, setResults] = useState<TMember[]>([]);
  const [members, setMembers] = useState<TMember[]>([]);

  const slug = workspace?.slug;
  const loadMembers = () =>
    slug ? godModeService.searchWorkspaceUsers(slug, "").then(setMembers, () => setMembers([])) : Promise.resolve();
  useEffect(() => {
    if (dialog === "assign") void loadMembers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dialog, slug]);

  // debounced user search while the assign dialog is open
  useEffect(() => {
    if (dialog !== "assign" || !slug || !email.trim() || email === selectedEmail) return;
    const timer = setTimeout(() => {
      godModeService
        .searchWorkspaceUsers(slug, email.trim())
        .then(setResults)
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [dialog, slug, email, selectedEmail]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!workspace) return null;

  const close = () => {
    setDialog(null);
    setConfirmText("");
    setEmail("");
    setSelectedEmail("");
    setResults([]);
    setRole(15);
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

  // assign / change role keeps the dialog open so several users can be handled in one go
  const assign = async (userEmail: string, newRole: number) => {
    try {
      const { created } = await godModeService.assignWorkspaceMember(workspace.slug, userEmail, newRole);
      setToast({
        type: "success",
        title: "Success",
        message: `${userEmail} ${created ? "added to" : "is now " + ROLE_LABELS[newRole] + " in"} "${workspace.name}".`,
      });
      return true;
    } catch (error: any) {
      setToast({ type: "error", title: "Error", message: error?.error ?? "Failed to update member." });
      return false;
    }
  };

  const handleAssign = async () => {
    setIsSubmitting(true);
    if (await assign(email.trim(), role)) {
      setEmail("");
      setSelectedEmail("");
      setResults([]);
      await loadMembers();
    }
    setIsSubmitting(false);
  };

  const handleRoleChange = async (member: TMember, newRole: number) => {
    if (await assign(member.email, newRole))
      setMembers((prev) => prev.map((m) => (m.id === member.id ? { ...m, current_role: newRole } : m)));
  };

  return (
    <div className="flex items-center gap-2">
      <ConfirmDialog
        isOpen={dialog === "assign"}
        handleClose={close}
        handleSubmit={handleAssign}
        isSubmitting={isSubmitting}
        isDisabled={!selectedEmail || email !== selectedEmail}
        variant="primary"
        title="Manage members"
        content={
          <div className="flex flex-col gap-3">
            <span>
              Add an existing user to <b>{workspace.name}</b>.
            </span>
            <Input
              size="lg"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Search by name or email"
              autoComplete="off"
            />
            {results.length > 0 && email !== selectedEmail && (
              <div className="max-h-48 overflow-y-auto rounded-md border border-subtle">
                {results.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-body-sm-regular hover:bg-layer-2"
                    onClick={() => {
                      setEmail(u.email);
                      setSelectedEmail(u.email);
                      if (u.current_role) setRole(u.current_role);
                    }}
                  >
                    <span className="truncate">
                      {u.display_name} <span className="text-tertiary">{u.email}</span>
                    </span>
                    {u.current_role && <span className="shrink-0 text-tertiary">{ROLE_LABELS[u.current_role]}</span>}
                  </button>
                ))}
              </div>
            )}
            <select
              className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-sm-regular text-primary"
              value={role}
              onChange={(e) => setRole(Number(e.target.value))}
            >
              <option value={20}>Admin</option>
              <option value={15}>Member</option>
              <option value={5}>Guest</option>
            </select>
            {members.length > 0 && (
              <div className="flex flex-col gap-1 border-t border-subtle pt-3">
                <span className="text-body-xs-medium text-tertiary">Current members ({members.length})</span>
                <div className="max-h-56 overflow-y-auto">
                  {members.map((m) => (
                    <div key={m.id} className="flex items-center justify-between gap-2 py-1.5">
                      <span className="truncate text-body-sm-regular" title={m.email}>
                        {m.display_name} <span className="text-tertiary">{m.email}</span>
                      </span>
                      <select
                        className="shrink-0 rounded-md border border-subtle bg-layer-2 px-2 py-1 text-body-xs-regular text-primary"
                        value={m.current_role ?? 15}
                        onChange={(e) => handleRoleChange(m, Number(e.target.value))}
                      >
                        <option value={20}>Admin</option>
                        <option value={15}>Member</option>
                        <option value={5}>Guest</option>
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        }
        primaryButtonText={{ loading: "Assigning", default: "Assign" }}
      />
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
      <Button variant="secondary" size="sm" stretch="auto" label="Members" onClick={() => setDialog("assign")} />
      <Menu>
        <MenuTrigger
          render={
            <IconButton
              variant="ghost"
              size="sm"
              aria-label="More actions"
              icon={<Icon icon={<MoreVerticalOutline />} />}
            />
          }
        />
        <MenuContent side="bottom" align="end">
          <MenuItem label="Archive all projects" onClick={() => setDialog("archive")} />
          <MenuItem label="Delete workspace" onClick={() => setDialog("delete")} />
        </MenuContent>
      </Menu>
    </div>
  );
});
