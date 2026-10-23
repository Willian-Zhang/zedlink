declare module "react-dom/client" {
  import type { ReactNode } from "react";
  export function createRoot(container: Element): { render(children: ReactNode): void };
}

declare module "react-dom" {
  export function flushSync(callback: () => void): void;
}
