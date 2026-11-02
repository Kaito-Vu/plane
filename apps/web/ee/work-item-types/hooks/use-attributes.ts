import { useContext, useEffect } from "react";
import { StoreContext } from "@/lib/store-context";
import type { IAttributeStore } from "../store/attribute.store";

export const useAttributes = (): IAttributeStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useAttributes must be used within StoreProvider");
  return context.attribute;
};

/** Loads a project's agile types and attributes once per session. */
export const useEnsureProjectTypes = (workspaceSlug: string | undefined, projectId: string | null | undefined) => {
  const { ensureProject } = useAttributes();
  useEffect(() => {
    if (workspaceSlug && projectId) void ensureProject(workspaceSlug, projectId);
  }, [workspaceSlug, projectId, ensureProject]);
};
