#!/usr/bin/env node
// Read-only install check. Never print a credential, request, or thread title.
import { GatewayClient } from "../server/connection.mjs";

const env = process.env;
try {
  const gateway = new GatewayClient({
    baseUrl: env.ZEDLINK_PASEO_URL ?? "",
    targetId: env.ZEDLINK_PASEO_TARGET_ID ?? "",
    credentialFile: env.ZEDLINK_PASEO_CREDENTIAL_FILE ?? "",
    caFile: env.ZEDLINK_PASEO_CA_FILE,
  });
  const listed = await gateway.list();
  if (!listed || typeof listed.instance_id !== "string" || typeof listed.epoch !== "string" ||
      !Array.isArray(listed.threads)) throw new Error("Invalid native thread list");
  const nativeCount = listed.threads.filter((row) => row?.agent?.kind === "zed" &&
    typeof row.thread_id === "string").length;
  console.log(`Gateway TLS, paired device, and target: OK. Exposed native Zed threads: ${nativeCount}.`);
  if (nativeCount === 0) {
    console.error("Expose an existing native Zed Agent thread with /remote-control before opening Paseo.");
    process.exitCode = 2;
  }
} catch (error) {
  const code = typeof error === "object" && error && "code" in error ? error.code : "CHECK_FAILED";
  console.error(`ZedLink Paseo preflight failed (${String(code)}). Check the gateway, TLS trust, target, and private paired-device file.`);
  process.exitCode = 1;
}
