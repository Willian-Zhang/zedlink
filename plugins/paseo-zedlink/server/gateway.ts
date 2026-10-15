import { randomUUID } from "node:crypto";
import { readFile, lstat } from "node:fs/promises";
import { request as httpsRequest } from "node:https";

const MAX_RESPONSE = 4 * 1024 * 1024;

export class GatewayError extends Error {
  constructor(message: string, public code = "GATEWAY_ERROR") {
    super(message);
  }
}

function endpoint(value: string): URL {
  const url = new URL(value);
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.search || url.hash) {
    throw new GatewayError("A plain HTTPS gateway URL is required", "INVALID_ENDPOINT");
  }
  return url;
}

async function credentials(path: string) {
  const meta = await lstat(path);
  if (!meta.isFile() || meta.isSymbolicLink() || (meta.mode & 0o077) !== 0) {
    throw new GatewayError("The credential file must be a private regular file (mode 0600)", "INVALID_CREDENTIAL_FILE");
  }
  const value = JSON.parse(await readFile(path, "utf8"));
  if (![value.gateway_id, value.device_id, value.token].every((field) => typeof field === "string" && field.length > 0)) {
    throw new GatewayError("The credential file needs gateway_id, device_id, and token", "INVALID_CREDENTIAL_FILE");
  }
  return value as { gateway_id: string; device_id: string; token: string };
}

export class GatewayClient {
  readonly base: URL;
  readonly targetId: string;
  readonly credentialFile: string;
  readonly caFile?: string;

  constructor(config: { baseUrl: string; targetId: string; credentialFile: string; caFile?: string }) {
    this.base = endpoint(config.baseUrl);
    if (!config.targetId || !config.credentialFile) throw new GatewayError("Target and credential file are required", "INVALID_CONFIG");
    this.targetId = config.targetId;
    this.credentialFile = config.credentialFile;
    this.caFile = config.caFile;
  }

  private async http(path: string, body?: unknown, token?: string): Promise<any> {
    const url = new URL(this.base);
    url.pathname = `${this.base.pathname.replace(/\/$/, "")}${path}`;
    const ca = this.caFile ? await readFile(this.caFile) : undefined;
    const data = body === undefined ? undefined : Buffer.from(JSON.stringify(body));
    return await new Promise((resolve, reject) => {
      const req = httpsRequest(url, {
        method: data ? "POST" : "GET",
        ca,
        headers: {
          Accept: "application/json",
          ...(data ? { "Content-Type": "application/json", "Content-Length": data.length } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        timeout: 10_000,
      }, (res) => {
        const parts: Buffer[] = [];
        let size = 0;
        res.on("data", (chunk: Buffer) => {
          size += chunk.length;
          if (size > MAX_RESPONSE) {
            req.destroy(new GatewayError("Gateway response is too large", "PAYLOAD_TOO_LARGE"));
            return;
          }
          parts.push(chunk);
        });
        res.on("end", () => {
          if ((res.statusCode ?? 0) >= 300 && (res.statusCode ?? 0) < 400) {
            reject(new GatewayError("Gateway redirect refused", "REDIRECT_REFUSED"));
            return;
          }
          let value: any;
          try { value = JSON.parse(Buffer.concat(parts).toString("utf8")); }
          catch { reject(new GatewayError("Invalid gateway JSON", "INVALID_RESPONSE")); return; }
          if (res.statusCode !== 200) {
            reject(new GatewayError(`Gateway HTTP ${res.statusCode}`, value?.error?.code ?? value?.error ?? "HTTP_ERROR"));
            return;
          }
          resolve(value);
        });
      });
      req.on("timeout", () => req.destroy(new GatewayError("Gateway timed out", "TIMEOUT")));
      req.on("error", reject);
      if (data) req.write(data);
      req.end();
    });
  }

  async identity(): Promise<string> {
    const info = await this.http("/v1/gateway");
    if (info?.version !== 1 || typeof info.gateway_id !== "string") {
      throw new GatewayError("Invalid gateway identity", "INVALID_RESPONSE");
    }
    return info.gateway_id;
  }

  async rpc(method: string, params: Record<string, unknown>, requestId = randomUUID()): Promise<any> {
    const expected = await credentials(this.credentialFile);
    const actual = await this.identity();
    if (actual !== expected.gateway_id) throw new GatewayError("Gateway identity changed; credential withheld", "GATEWAY_MISMATCH");
    const envelope = { version: 1, request_id: requestId, target_id: this.targetId, method, params };
    const response = await this.http("/v1/rpc", envelope, expected.token);
    if (response?.version !== 1 || response.request_id !== requestId) {
      throw new GatewayError("Gateway response identity mismatch", "INVALID_RESPONSE");
    }
    if (response.error) {
      const code = typeof response.error === "string" ? response.error : response.error.code;
      throw new GatewayError(`ZedLink ${code ?? "error"}`, code ?? "RPC_ERROR");
    }
    return response.result;
  }

  list() { return this.rpc("thread.list", {}); }
  snapshot(threadId: string, instanceId: string, epoch: string) {
    return this.rpc("thread.snapshot", { instance_id: instanceId, epoch, thread_id: threadId });
  }
  settings(threadId: string, instanceId: string, epoch: string) {
    return this.rpc("thread.settings", { instance_id: instanceId, epoch, thread_id: threadId });
  }
  history(threadId: string, instanceId: string, epoch: string, before: number) {
    return this.rpc("thread.history", { instance_id: instanceId, epoch, thread_id: threadId, before_entry_index: before });
  }
  events(threadId: string, instanceId: string, epoch: string, afterSequence: number) {
    return this.rpc("thread.events", { instance_id: instanceId, epoch, thread_id: threadId, after_sequence: afterSequence });
  }
  send(threadId: string, instanceId: string, epoch: string, text: string, requestId: string) {
    return this.rpc("thread.send", { instance_id: instanceId, epoch, thread_id: threadId, text }, requestId);
  }
  status(instanceId: string, epoch: string, requestId: string) {
    return this.rpc("request.status", { instance_id: instanceId, epoch, original_request_id: requestId });
  }
  removeQueued(threadId: string, instanceId: string, epoch: string, requestId: string, queueEntryId: number) {
    return this.rpc("thread.queue.remove", { instance_id: instanceId, epoch, thread_id: threadId,
      original_request_id: requestId, queue_entry_id: queueEntryId });
  }
  cancel(threadId: string, instanceId: string, epoch: string, turnId: number) {
    return this.rpc("thread.cancel", { instance_id: instanceId, epoch, thread_id: threadId, turn_id: turnId });
  }
  approvals(threadId: string, instanceId: string, epoch: string) {
    return this.rpc("thread.approvals", { instance_id: instanceId, epoch, thread_id: threadId });
  }
  respondApproval(threadId: string, instanceId: string, epoch: string, approvalId: string, turnId: number,
    optionId: string, choiceIndex?: number, subagentId?: string) {
    return this.rpc("approval.respond", { instance_id: instanceId, epoch, thread_id: threadId,
      approval_id: approvalId, turn_id: turnId, option_id: optionId,
      ...(choiceIndex === undefined ? {} : { choice_index: choiceIndex }),
      ...(subagentId === undefined ? {} : { subagent_id: subagentId }),
    });
  }
}

export function fromEnvironment(env = process.env) {
  return new GatewayClient({
    baseUrl: env.ZEDLINK_PASEO_URL ?? "",
    targetId: env.ZEDLINK_PASEO_TARGET_ID ?? "",
    credentialFile: env.ZEDLINK_PASEO_CREDENTIAL_FILE ?? "",
    caFile: env.ZEDLINK_PASEO_CA_FILE,
  });
}
