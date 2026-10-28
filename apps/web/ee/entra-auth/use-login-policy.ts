/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useLocation } from "react-router";
import type { TOAuthOption } from "@plane/types";
import { EAuthenticationErrorCodes as E } from "@/helpers/authentication.helper";
import { useInstance } from "@/hooks/store/use-instance";

export const INTERNAL_LOGIN_PATH = "/login/internal";

// error codes raised by the email/password/magic-code flow: these belong on /login/internal
const EMAIL_FLOW_ERROR_CODES: string[] = new Set([
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
  const done = useRef(false);
  const enabled = oAuthOptions.filter((o) => o.enabled !== false);
  const p = computeLoginPolicy({
    ssoOnly: config?.sso_only_login_page,
    pathname,
    enabledProviderIds: enabled.map((o) => o.id),
    errorCode: searchParams.get("error_code"),
    noRedirect: searchParams.get("no_redirect") === "1",
  });
  const target = enabled.find((o) => o.id === p.autoRedirectProviderId);
  const autoRedirect = target
    ? () => {
        if (done.current) return; // StrictMode / re-render guard
        done.current = true;
        target.onClick();
      }
    : null;
  return { hideEmailForm: p.hideEmailForm, autoRedirect, redirectToInternal: p.redirectToInternal };
};
