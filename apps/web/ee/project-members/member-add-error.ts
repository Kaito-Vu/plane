const BASE = "project_settings.members.invite_members.errors";

// Maps a failed bulk-add to an i18n key. Backend codes: USER_NOT_ELIGIBLE, ALREADY_MEMBER, ROLE_NOT_ALLOWED; core
// answers a workspace-role mismatch with an uncoded English 400 ("...role higher/lower than the workspace role").
export const memberAddErrorKey = (error: unknown): string => {
  const e = (error ?? {}) as { code?: string; error?: string };
  switch (e.code) {
    case "USER_NOT_ELIGIBLE":
      return `${BASE}.not_eligible`;
    case "ALREADY_MEMBER":
      return `${BASE}.already_member`;
    case "ROLE_NOT_ALLOWED":
      return `${BASE}.role_not_allowed`;
  }
  if (typeof e.error === "string") {
    if (/role (higher|lower) than the workspace role/i.test(e.error)) return `${BASE}.role_conflict`;
    if (/^invalid role/i.test(e.error)) return `${BASE}.role_not_allowed`;
  }
  return `${BASE}.generic`;
};
