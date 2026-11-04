import { useEffect, useState } from "react";
import { projectMemberSearchService } from "./services/project-member-search.service";

// Module-level cache: fetched once per page load. False while loading and on error.
let cached: Promise<boolean> | undefined;

export const useExternalInvitesEnabled = (): boolean => {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let active = true;
    cached ??= projectMemberSearchService.externalInvitesEnabled();
    void cached.then((v) => active && setEnabled(v));
    return () => {
      active = false;
    };
  }, []);
  return enabled;
};
