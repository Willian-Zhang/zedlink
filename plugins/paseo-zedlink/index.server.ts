import type { PluginServerContext } from "@getpaseo/plugin/server";
import { negotiateProviderCapabilities, type ProviderRegistration } from "@getpaseo/plugin/server/provider";
import { createConnection } from "./server/connection.mjs";

const supported = ["prompt.message", "session.persistence", "permission"] as const;

const provider: ProviderRegistration = {
  id: "zedlink",
  label: "ZedLink",
  description: "Continue an explicitly exposed Zed thread",
  async connect(request) {
    if (!request.versions.includes(1)) throw new Error("Paseo provider protocol v1 is required");
    return createConnection(negotiateProviderCapabilities(request.capabilities, supported));
  },
};

export default function contribute(server: PluginServerContext) {
  server.registerProvider(provider);
  return () => {};
}
