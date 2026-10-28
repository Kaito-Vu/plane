import { observer } from "mobx-react";
import { Input } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { useMember } from "@/hooks/store/use-member";
import type { TAttributeFieldType, TAttributeOption } from "../../types";

export const FIELD_TYPES: TAttributeFieldType[] = [
  "text",
  "textarea",
  "number",
  "boolean",
  "date",
  "datetime",
  "url",
  "select",
  "multi_select",
  "member",
  "multi_member",
];

export const OPTION_FIELD_TYPES: TAttributeFieldType[] = ["select", "multi_select"];

type TEditorProps<T> = { value: T; onChange: (v: T) => void; id?: string };

const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));
const arr = (v: unknown) => (Array.isArray(v) ? v.map(String) : []);
const selected = (e: React.ChangeEvent<HTMLSelectElement>) => Array.from(e.target.selectedOptions, (o) => o.value);
const SELECT_CLASS = "w-full rounded-md border border-subtle bg-surface-1 px-2 py-1.5 text-13";

// One editor per field_type (spec §4). Empty input means "no default" (null).
function TextEditor({ value, onChange, id }: TEditorProps<unknown>) {
  return <Input size="md" id={id} value={str(value)} onChange={(e) => onChange(e.target.value || null)} />;
}

function TextareaEditor({ value, onChange, id }: TEditorProps<unknown>) {
  return (
    <textarea
      id={id}
      className={`${SELECT_CLASS} min-h-20`}
      value={str(value)}
      onChange={(e) => onChange(e.target.value || null)}
    />
  );
}

function NumberEditor({ value, onChange, id }: TEditorProps<unknown>) {
  // sent as a string: the backend stores a Decimal (16 integer + 4 decimal digits)
  return (
    <Input size="md" id={id} type="number" value={str(value)} onChange={(e) => onChange(e.target.value || null)} />
  );
}

function BooleanEditor({ value, onChange }: TEditorProps<unknown>) {
  return <Switch size="md" checked={value === true} onCheckedChange={(v: boolean) => onChange(v)} />;
}

function DateEditor({ value, onChange, id }: TEditorProps<unknown>) {
  return <Input size="md" id={id} type="date" value={str(value)} onChange={(e) => onChange(e.target.value || null)} />;
}

function DatetimeEditor({ value, onChange, id }: TEditorProps<unknown>) {
  return (
    <Input
      size="md"
      id={id}
      type="datetime-local"
      value={str(value).slice(0, 16)}
      onChange={(e) => onChange(e.target.value || null)}
    />
  );
}

function UrlEditor({ value, onChange, id }: TEditorProps<unknown>) {
  return <Input size="md" id={id} type="url" value={str(value)} onChange={(e) => onChange(e.target.value || null)} />;
}

function SelectEditor({ value, onChange, id, options }: TEditorProps<unknown> & { options: TAttributeOption[] }) {
  return (
    <select id={id} className={SELECT_CLASS} value={str(value)} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">—</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </select>
  );
}

function MultiSelectEditor({ value, onChange, id, options }: TEditorProps<unknown> & { options: TAttributeOption[] }) {
  return (
    <select id={id} multiple className={SELECT_CLASS} value={arr(value)} onChange={(e) => onChange(selected(e))}>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </select>
  );
}

const MemberEditor = observer(function MemberEditor({
  value,
  onChange,
  id,
  multiple,
}: TEditorProps<unknown> & { multiple?: boolean }) {
  const {
    getUserDetails,
    workspace: { workspaceMemberIds },
  } = useMember();
  const members = (workspaceMemberIds ?? []).map((uid) => (
    <option key={uid} value={uid}>
      {getUserDetails(uid)?.display_name ?? uid}
    </option>
  ));
  if (multiple)
    return (
      <select id={id} multiple className={SELECT_CLASS} value={arr(value)} onChange={(e) => onChange(selected(e))}>
        {members}
      </select>
    );
  return (
    <select id={id} className={SELECT_CLASS} value={str(value)} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">—</option>
      {members}
    </select>
  );
});

type TProps = TEditorProps<unknown> & { fieldType: TAttributeFieldType; options: TAttributeOption[] };

export function AttributeValueEditor({ fieldType, options, ...rest }: TProps) {
  const activeOptions = options.filter((o) => o.is_active);
  switch (fieldType) {
    case "text":
      return <TextEditor {...rest} />;
    case "textarea":
      return <TextareaEditor {...rest} />;
    case "number":
      return <NumberEditor {...rest} />;
    case "boolean":
      return <BooleanEditor {...rest} />;
    case "date":
      return <DateEditor {...rest} />;
    case "datetime":
      return <DatetimeEditor {...rest} />;
    case "url":
      return <UrlEditor {...rest} />;
    case "select":
      return <SelectEditor {...rest} options={activeOptions} />;
    case "multi_select":
      return <MultiSelectEditor {...rest} options={activeOptions} />;
    case "member":
      return <MemberEditor {...rest} />;
    case "multi_member":
      return <MemberEditor {...rest} multiple />;
  }
}
