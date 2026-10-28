import { useContext } from "react";
import { StoreContext } from "@/lib/store-context";
import type { IAttributeStore } from "../store/attribute.store";

export const useAttributes = (): IAttributeStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useAttributes must be used within StoreProvider");
  return context.attribute;
};
