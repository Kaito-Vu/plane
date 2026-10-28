/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useLocation } from "react-router";
import type { TOAuthOption } from "@plane/types";
import { EAuthenticationErrorCodes as E } from "@/helpers/authentication.helper";
import { INTERNAL_LOGIN_PATH } from "./constants";
import { getEntraLoginUrl } from "./use-entra-oauth-config";
import { useInstance } from "@/hooks/store/use-instance";

export { INTERNAL_LOGIN_PATH };

// error codes raised by the email/password/magic-code flow: these belong on /login/internal
const EMAIL_FLOW_ERROR_CODES = new Set<string>([
  E.INVALID_EMAIL,
  E.EMAIL_REQUIRED,
  E.SIGNUP_DISABLED,
  E.USER_ACCOUNT_DEACTIVATED,
  E.PASSWORD_TOO_WEAK,
  E.SMTP_NOT_CONFIGURED,
  E.USER_ALREADY_EXIST,
  E.USER_DOES_NOT_EXIST,
  "5900", // RATE_LIMIT_EXCEEDED (not in the web enum)
  E.AUTHENTICATION_FAILED_SIGN_IN,
  E.AUTHENTICATION_FAILED_SIGN_UP,
  E.INVALID_PASSWORD,
  E.REQUIRED_EMAIL_PASSWORD_SIGN_IN,
  E.REQUIRED_EMAIL_PASSWORD_SIGN_UP,
  E.INVALID_EMAIL_SIGN_IN,
  E.INVALID_EMAIL_SIGN_UP,
  E.INVALID_EMAIL_MAGIC_SIGN_IN,
  E.INVALID_EMAIL_MAGIC_SIGN_UP,
  E.MAGIC_SIGN_IN_EMAIL_CODE_REQUIRED,
  E.MAGIC_SIGN_UP_EMAIL_CODE_REQUIRED,
  E.INVALID_MAGIC_CODE_SIGN_IN,
  E.INVALID_MAGIC_CODE_SIGN_UP,
  E.EXPIRED_MAGIC_CODE_SIGN_IN,
  E.EXPIRED_MAGIC_CODE_SIGN_UP,
  E.EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_IN,
  E.EMAIL_CODE_ATTEMPT_EXHAUSTED_SIGN_UP,
  E.MAGIC_LINK_LOGIN_DISABLED,
  E.PASSWORD_LOGIN_DISABLED,
]);

export type TLoginPolicyInput = {
  ssoOnly: boolean | undefined;
  pathname: string;
  enabledProviderIds: string[];
  errorCode: string | null;
  noRedirect: boolean;
};
export type TLoginPolicy = {
  hideEmailForm: boolean;
  autoRedirectProviderId: string | null;
  redirectToInternal: boolean;
};

const SHOW_FORM: TLoginPolicy = { hideEmailForm: false, autoRedirectProviderId: null, redirectToInternal: false };

export const computeLoginPolicy = (i: TLoginPolicyInput): TLoginPolicy => {
  if (!i.ssoOnly) return SHOW_FORM; // 1. flag off: unchanged
  if (i.pathname === INTERNAL_LOGIN_PATH) return SHOW_FORM; // 2. break-glass page
  if (i.enabledProviderIds.length === 0) return SHOW_FORM; // 3. never lock the instance
  const hide = { hideEmailForm: true, autoRedirectProviderId: null, redirectToInternal: false };
  if (i.errorCode) {
    // 4. email-flow errors go to the internal page; any other error stays here without redirecting
    return EMAIL_FLOW_ERROR_CODES.has(i.errorCode) ? { ...hide, redirectToInternal: true } : hide;
  }
  if (i.noRedirect) return hide; // 5.
  if (i.enabledProviderIds.length === 1) return { ...hide, autoRedirectProviderId: i.enabledProviderIds[0] }; // 6.
  return hide;
};

export const useLoginPolicy = (oAuthOptions: TOAuthOption[]) => {
  const { config } = useInstance();
  const searchParams = useSearchParams();
  const { pathname } = useLocation();
  const nextPath = searchParams.get("next_path");
  const done = useRef(false);
  const enabled = oAuthOptions.filter((o) => !!o.enabled);
  const p = computeLoginPolicy({
    ssoOnly: config?.sso_only_login_page,
    pathname,
    enabledProviderIds: enabled.map((o) => o.id),
    errorCode: searchParams.get("error_code"),
    noRedirect: searchParams.get("no_redirect") === "1",
  });
  const target = enabled.find((o) => o.id === p.autoRedirectProviderId);
  // ref guard: runs the redirect once even with StrictMode double effects / re-renders
  const autoRedirect = useCallback(() => {
    if (!target || done.current) return;
    done.current = true;
    // replace (not assign) so Browser Back from the IdP does not loop; only Entra exposes a plain URL
    if (target.id === "entra") window.location.replace(getEntraLoginUrl(nextPath));
    else target.onClick();
  }, [target, nextPath]);
  return {
    hideEmailForm: p.hideEmailForm,
    autoRedirect: target ? autoRedirect : null,
    redirectToInternal: p.redirectToInternal,
  };
};
