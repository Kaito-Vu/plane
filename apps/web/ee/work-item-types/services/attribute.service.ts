import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";
import type {
  TImportRow,
  TImportRowError,
  TAttribute,
  TProjectWorkItemType,
  TAttributeOption,
  TAttributeTemplate,
  TAttributeValues,
} from "../types";

type TOptionPayload = Partial<Omit<TAttributeOption, "id">>;

export class AttributeService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  // errors are the flat TEeError body
  private async req<T>(p: Promise<{ data: T }>): Promise<T> {
    return p
      .then((r) => r?.data)
      .catch((e) => {
        throw e?.response?.data;
      });
  }

  private ws = (slug: string) => `/api/workspaces/${slug}`;
  private proj = (slug: string, projectId: string) => `${this.ws(slug)}/projects/${projectId}/attributes`;

  // templates (workspace admin)
  getTemplates(slug: string) {
    return this.req<TAttributeTemplate[]>(this.get(`${this.ws(slug)}/attribute-templates/`));
  }
  createTemplate(slug: string, data: Partial<TAttributeTemplate>) {
    return this.req<TAttributeTemplate>(this.post(`${this.ws(slug)}/attribute-templates/`, data));
  }
  updateTemplate(slug: string, id: string, data: Partial<TAttributeTemplate>) {
    return this.req<TAttributeTemplate>(this.patch(`${this.ws(slug)}/attribute-templates/${id}/`, data));
  }
  deleteTemplate(slug: string, id: string) {
    return this.req<void>(this.delete(`${this.ws(slug)}/attribute-templates/${id}/`));
  }
  reorderTemplates(slug: string, ids: string[]) {
    return this.req<void>(this.post(`${this.ws(slug)}/attribute-templates/reorder/`, { ids }));
  }
  createTemplateOption(slug: string, id: string, data: TOptionPayload) {
    return this.req<TAttributeOption>(this.post(`${this.ws(slug)}/attribute-templates/${id}/options/`, data));
  }
  updateTemplateOption(slug: string, id: string, optionId: string, data: TOptionPayload) {
    return this.req<TAttributeOption>(
      this.patch(`${this.ws(slug)}/attribute-templates/${id}/options/${optionId}/`, data)
    );
  }
  deleteTemplateOption(slug: string, id: string, optionId: string) {
    return this.req<void>(this.delete(`${this.ws(slug)}/attribute-templates/${id}/options/${optionId}/`));
  }

  // project attributes
  getAttributes(slug: string, projectId: string, issueTypeId?: string) {
    return this.req<TAttribute[]>(
      this.get(`${this.proj(slug, projectId)}/`, issueTypeId ? { params: { issue_type_id: issueTypeId } } : undefined)
    );
  }
  createAttribute(slug: string, projectId: string, data: Partial<TAttribute>) {
    return this.req<TAttribute>(this.post(`${this.proj(slug, projectId)}/`, data));
  }
  updateAttribute(slug: string, projectId: string, id: string, data: Partial<TAttribute>) {
    return this.req<TAttribute>(this.patch(`${this.proj(slug, projectId)}/${id}/`, data));
  }
  deleteAttribute(slug: string, projectId: string, id: string) {
    return this.req<void>(this.delete(`${this.proj(slug, projectId)}/${id}/`));
  }
  reorderAttributes(slug: string, projectId: string, ids: string[], issueTypeId?: string) {
    return this.req<void>(this.post(`${this.proj(slug, projectId)}/reorder/`, { ids, issue_type_id: issueTypeId }));
  }
  applyTemplate(slug: string, projectId: string, templateId: string, issueTypeId: string) {
    return this.req<TAttribute>(
      this.post(`${this.proj(slug, projectId)}/apply-template/`, {
        template_id: templateId,
        issue_type_id: issueTypeId,
      })
    );
  }
  createOption(slug: string, projectId: string, id: string, data: TOptionPayload) {
    return this.req<TAttributeOption>(this.post(`${this.proj(slug, projectId)}/${id}/options/`, data));
  }
  updateOption(slug: string, projectId: string, id: string, optionId: string, data: TOptionPayload) {
    return this.req<TAttributeOption>(this.patch(`${this.proj(slug, projectId)}/${id}/options/${optionId}/`, data));
  }
  deleteOption(slug: string, projectId: string, id: string, optionId: string) {
    return this.req<void>(this.delete(`${this.proj(slug, projectId)}/${id}/options/${optionId}/`));
  }

  fetchProjectTypes(slug: string, projectId: string) {
    return this.req<TProjectWorkItemType[]>(this.get(`${this.ws(slug)}/projects/${projectId}/work-item-types/`));
  }

  // values
  getAttributeValues(slug: string, projectId: string, issueId: string) {
    return this.req<TAttributeValues>(
      this.get(`${this.ws(slug)}/projects/${projectId}/issues/${issueId}/attribute-values/`)
    );
  }

  updateAttributeValues(slug: string, projectId: string, issueId: string, values: TAttributeValues) {
    return this.req<unknown>(
      this.patch(`${this.ws(slug)}/projects/${projectId}/issues/${issueId}/`, { attribute_values: values })
    );
  }

  /** All live descendants of an issue (delete/archive confirm). */
  getSubtreeCount(slug: string, projectId: string, issueId: string, forArchive = false) {
    return this.req<{ count: number }>(
      this.get(
        `${this.ws(slug)}/projects/${projectId}/issues/${issueId}/subtree-count/`,
        forArchive ? { params: { for: "archive" } } : {}
      )
    );
  }

  // two-step import (ImportBatch / ImportRow staging)
  private imports = (slug: string, projectId: string) => `${this.ws(slug)}/projects/${projectId}/imports`;
  createImportBatch(slug: string, projectId: string) {
    return this.req<{ id: string; status: string }>(this.post(`${this.imports(slug, projectId)}/`, {}));
  }
  addImportRows(slug: string, projectId: string, batchId: string, rows: Record<string, unknown>[]) {
    return this.req<TImportRow[]>(this.post(`${this.imports(slug, projectId)}/${batchId}/rows/`, { rows }));
  }
  updateImportRow(slug: string, projectId: string, batchId: string, rowId: string, data: Record<string, unknown>) {
    return this.req<TImportRow>(this.patch(`${this.imports(slug, projectId)}/${batchId}/rows/${rowId}/`, data));
  }
  validateImport(slug: string, projectId: string, batchId: string) {
    return this.req<{ valid: boolean; errors: TImportRowError[] }>(
      this.post(`${this.imports(slug, projectId)}/${batchId}/validate/`, {})
    );
  }
  commitImport(slug: string, projectId: string, batchId: string) {
    return this.req<{ created: Record<string, string>; errors: TImportRowError[] }>(
      this.post(`${this.imports(slug, projectId)}/${batchId}/commit/`, {})
    );
  }
}
