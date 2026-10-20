import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import { inicial, reducir, type Accion, type Estado } from "./reductor.ts";

export type { Accion, Estado, Paso } from "./reductor.ts";
export { inicial } from "./reductor.ts";

const Ctx = createContext<{ e: Estado; d: Dispatch<Accion> } | null>(null);

export function Proveedor({ children }: { children: ReactNode }) {
  const [e, d] = useReducer(reducir, inicial);
  return <Ctx.Provider value={{ e, d }}>{children}</Ctx.Provider>;
}

export function useStore() {
  const c = useContext(Ctx);
  if (!c) throw new Error("Falta el proveedor de estado");
  return c;
}
