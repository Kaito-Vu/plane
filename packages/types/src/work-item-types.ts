/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TLogoProps } from "./common";

export type TWorkItemProcess = "scrum" | "agile";

export type TIssueType = {
  id: string;
  name: string;
  description: string;
  logo_props: TLogoProps;
  is_epic: boolean;
  is_default: boolean;
  is_active: boolean;
  /** 0..9 — a parent must have a higher level than its child; 0 is a sub-task. */
  level: number;
  is_preset: boolean;
  /** Preset key ("epic", "user_story", …) or null for custom types. */
  external_id: string | null;
  /** Icon colour vs background contrast below 4.5:1. */
  low_contrast?: boolean;
};

export type TProjectIssueType = TIssueType & { is_project_default: boolean };

export type TProjectWorkItemTypes = {
  /** null = assigned types match neither preset process ("custom"). */
  process: TWorkItemProcess | null;
  enabled: boolean;
  types: TProjectIssueType[];
};

/** 409 body of DELETE work-item-types/<id>/ and of the project process / assign endpoints. */
export type TIssueTypeConflict = {
  error: string;
  code?: "process_change_blocked" | "process_conflict";
  count?: number;
};

/** GET work-item-types/<id>/usage/ */
export type TIssueTypeUsage = { issues: number; drafts: number; count: number; projects: string[] };
