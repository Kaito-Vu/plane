import { Input, InputGroup } from "@makeplane/propel/components/input";
import type { InputProps } from "@makeplane/propel/components/input";

/** propel's bare `Input` draws no border; `InputGroup` supplies the field chrome. */
export function BorderedInput({ size = "md", ...props }: InputProps) {
  return (
    <InputGroup size={size}>
      <Input size={size} {...props} />
    </InputGroup>
  );
}
