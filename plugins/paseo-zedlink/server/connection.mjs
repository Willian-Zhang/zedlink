import { randomUUID } from "node:crypto";
import { lstat, readFile } from "node:fs/promises";
import { request } from "node:https";
//#region server/gateway.ts
const MAX_RESPONSE = 4 * 1024 * 1024;
var GatewayError = class extends Error {
	constructor(message, code = "GATEWAY_ERROR") {
		super(message);
		this.code = code;
	}
};
function endpoint(value) {
	const url = new URL(value);
	if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.search || url.hash) throw new GatewayError("A plain HTTPS gateway URL is required", "INVALID_ENDPOINT");
	return url;
}
async function credentials(path) {
	const meta = await lstat(path);
	if (!meta.isFile() || meta.isSymbolicLink() || (meta.mode & 63) !== 0) throw new GatewayError("The credential file must be a private regular file (mode 0600)", "INVALID_CREDENTIAL_FILE");
	const value = JSON.parse(await readFile(path, "utf8"));
	if (![
		value.gateway_id,
		value.device_id,
		value.token
	].every((field) => typeof field === "string" && field.length > 0)) throw new GatewayError("The credential file needs gateway_id, device_id, and token", "INVALID_CREDENTIAL_FILE");
	return value;
}
var GatewayClient = class {
	base;
	targetId;
	credentialFile;
	caFile;
	constructor(config) {
		this.base = endpoint(config.baseUrl);
		if (!config.targetId || !config.credentialFile) throw new GatewayError("Target and credential file are required", "INVALID_CONFIG");
		this.targetId = config.targetId;
		this.credentialFile = config.credentialFile;
		this.caFile = config.caFile;
	}
	async http(path, body, token) {
		const url = new URL(this.base);
		url.pathname = `${this.base.pathname.replace(/\/$/, "")}${path}`;
		const ca = this.caFile ? await readFile(this.caFile) : void 0;
		const data = body === void 0 ? void 0 : Buffer.from(JSON.stringify(body));
		return await new Promise((resolve, reject) => {
			const req = request(url, {
				method: data ? "POST" : "GET",
				ca,
				headers: {
					Accept: "application/json",
					...data ? {
						"Content-Type": "application/json",
						"Content-Length": data.length
					} : {},
					...token ? { Authorization: `Bearer ${token}` } : {}
				},
				timeout: 1e4
			}, (res) => {
				const parts = [];
				let size = 0;
				res.on("data", (chunk) => {
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
					let value;
					try {
						value = JSON.parse(Buffer.concat(parts).toString("utf8"));
					} catch {
						reject(new GatewayError("Invalid gateway JSON", "INVALID_RESPONSE"));
						return;
					}
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
	async identity() {
		const info = await this.http("/v1/gateway");
		if (info?.version !== 1 || typeof info.gateway_id !== "string") throw new GatewayError("Invalid gateway identity", "INVALID_RESPONSE");
		return info.gateway_id;
	}
	async rpc(method, params, requestId = randomUUID()) {
		const expected = await credentials(this.credentialFile);
		if (await this.identity() !== expected.gateway_id) throw new GatewayError("Gateway identity changed; credential withheld", "GATEWAY_MISMATCH");
		const envelope = {
			version: 1,
			request_id: requestId,
			target_id: this.targetId,
			method,
			params
		};
		const response = await this.http("/v1/rpc", envelope, expected.token);
		if (response?.version !== 1 || response.request_id !== requestId) throw new GatewayError("Gateway response identity mismatch", "INVALID_RESPONSE");
		if (response.error) {
			const code = typeof response.error === "string" ? response.error : response.error.code;
			throw new GatewayError(`ZedLink ${code ?? "error"}`, code ?? "RPC_ERROR");
		}
		return response.result;
	}
	list() {
		return this.rpc("thread.list", {});
	}
	snapshot(threadId, instanceId, epoch) {
		return this.rpc("thread.snapshot", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId
		});
	}
	settings(threadId, instanceId, epoch) {
		return this.rpc("thread.settings", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId
		});
	}
	history(threadId, instanceId, epoch, before) {
		return this.rpc("thread.history", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId,
			before_entry_index: before
		});
	}
	events(threadId, instanceId, epoch, afterSequence) {
		return this.rpc("thread.events", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId,
			after_sequence: afterSequence
		});
	}
	send(threadId, instanceId, epoch, text, requestId) {
		return this.rpc("thread.send", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId,
			text
		}, requestId);
	}
	status(instanceId, epoch, requestId) {
		return this.rpc("request.status", {
			instance_id: instanceId,
			epoch,
			original_request_id: requestId
		});
	}
	removeQueued(threadId, instanceId, epoch, requestId, queueEntryId) {
		return this.rpc("thread.queue.remove", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId,
			original_request_id: requestId,
			queue_entry_id: queueEntryId
		});
	}
	cancel(threadId, instanceId, epoch, turnId) {
		return this.rpc("thread.cancel", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId,
			turn_id: turnId
		});
	}
	approvals(threadId, instanceId, epoch) {
		return this.rpc("thread.approvals", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId
		});
	}
	respondApproval(threadId, instanceId, epoch, approvalId, turnId, optionId, choiceIndex, subagentId) {
		return this.rpc("approval.respond", {
			instance_id: instanceId,
			epoch,
			thread_id: threadId,
			approval_id: approvalId,
			turn_id: turnId,
			option_id: optionId,
			...choiceIndex === void 0 ? {} : { choice_index: choiceIndex },
			...subagentId === void 0 ? {} : { subagent_id: subagentId }
		});
	}
};
function fromEnvironment(env = process.env) {
	return new GatewayClient({
		baseUrl: env.ZEDLINK_PASEO_URL ?? "",
		targetId: env.ZEDLINK_PASEO_TARGET_ID ?? "",
		credentialFile: env.ZEDLINK_PASEO_CREDENTIAL_FILE ?? "",
		caFile: env.ZEDLINK_PASEO_CA_FILE
	});
}
//#endregion
//#region server/connection.ts
const traceStop = (stage) => {
	if (process.env.ZEDLINK_PASEO_TRACE_STOP === "1") console.info(`[paseo-zedlink] ${stage}`);
};
function modelId(threadId) {
	return `thread-${Buffer.from(threadId, "utf8").toString("base64url")}`;
}
function threadId(model) {
	if (!model.startsWith("thread-") || !/^[A-Za-z0-9_-]+$/.test(model.slice(7))) throw new Error("Choose an exposed ZedLink thread from the model list");
	const decoded = Buffer.from(model.slice(7), "base64url").toString("utf8");
	if (!decoded || modelId(decoded) !== model) throw new Error("Invalid ZedLink thread selection");
	return decoded;
}
function parseEntry(markdown, id, clientMessageId, meta) {
	if (markdown.startsWith("## User\n")) return [{
		type: "user_message",
		id,
		text: markdown.replace(/^## User\n+/, "").trim(),
		...clientMessageId ? { clientMessageId } : {}
	}];
	if (meta?.kind === "tool" && typeof meta.call_id === "string" && typeof meta.name === "string" && [
		"running",
		"completed",
		"failed",
		"canceled"
	].includes(meta.status)) return [{
		type: "tool_call",
		id,
		callId: `${id}:${meta.call_id}`,
		name: meta.name,
		status: meta.status,
		error: meta.status === "failed" ? "Native Zed tool failed" : null,
		detail: {
			type: "plain_text",
			label: meta.name,
			text: markdown.trim()
		}
	}];
	if (meta?.kind === "assistant" && Array.isArray(meta.segments) && meta.segments.every((part) => ["reasoning", "assistant"].includes(part?.kind) && typeof part.text === "string")) return meta.segments.map((part, index) => ({
		type: part.kind === "reasoning" ? "reasoning" : "assistant_message",
		id: `${id}:${index}`,
		text: part.text.trim()
	}));
	if (markdown.startsWith("## Assistant\n")) return [{
		type: "assistant_message",
		id,
		text: markdown.replace(/^## Assistant\n+/, "").trim()
	}];
	return [{
		type: "assistant_message",
		id,
		text: `Native Zed entry:\n\n${markdown.trim()}`
	}];
}
function validPage(page, session) {
	return page?.instance_id === session.instanceId && page.epoch === session.epoch && page.thread_id === session.threadId && Number.isSafeInteger(page.entry_start_index) && page.entry_start_index >= 0 && Number.isSafeInteger(page.entry_end_index) && page.entry_end_index >= page.entry_start_index && Array.isArray(page.entries_markdown) && page.entries_markdown.every((entry) => typeof entry === "string") && (page.entries_meta === void 0 || Array.isArray(page.entries_meta) && page.entries_meta.length === page.entries_markdown.length) && page.entry_start_index + page.entries_markdown.length === page.entry_end_index;
}
function restorePending(row) {
	if (typeof row?.requestId !== "string" || !row.requestId || typeof row.clientMessageId !== "string" || !row.clientMessageId || typeof row.instanceId !== "string" || !row.instanceId || typeof row.epoch !== "string" || !row.epoch || row.nativeRequestId !== void 0 && (typeof row.nativeRequestId !== "string" || !row.nativeRequestId) || row.queueEntryId !== void 0 && (!Number.isSafeInteger(row.queueEntryId) || row.queueEntryId < 0) || row.entryIndex !== void 0 && (!Number.isSafeInteger(row.entryIndex) || row.entryIndex < row.startIndex) || !Number.isSafeInteger(row.startIndex) || row.startIndex < 0) throw new Error("Invalid saved ZedLink request receipt");
	return {
		turnId: `zedlink:${row.requestId}`,
		clientMessageId: row.clientMessageId,
		requestId: row.requestId,
		nativeRequestId: row.nativeRequestId,
		queueEntryId: row.queueEntryId,
		entryIndex: row.entryIndex,
		startIndex: row.startIndex,
		instanceId: row.instanceId,
		epoch: row.epoch,
		text: "",
		matched: false,
		cancelRequested: row.cancelRequested === true
	};
}
function approvalKey(session, row) {
	return `zedlink:${Buffer.from(JSON.stringify([
		session.epoch,
		session.threadId,
		row?.subagent_id ?? null,
		row?.turn_id,
		row?.approval_id
	])).toString("base64url")}`;
}
function approvalFromNative(session, row) {
	if (row?.authorization_kind !== "permission_grant" || row.details_truncated !== false || typeof row.approval_id !== "string" || !row.approval_id || !Number.isSafeInteger(row.turn_id) || row.turn_id < 0 || typeof row.tool_name !== "string" || !row.tool_name || !row.raw_input || typeof row.raw_input !== "object" || Array.isArray(row.raw_input) || row.subagent_id !== void 0 && typeof row.subagent_id !== "string" || !Array.isArray(row.permission_options?.decisions)) return null;
	const actions = [];
	for (const [index, decision] of row.permission_options.decisions.entries()) {
		const behavior = decision?.option_kind === "allow_once" ? "allow" : decision?.option_kind === "reject_once" ? "deny" : null;
		if (!behavior || typeof decision.option_id !== "string" || !decision.option_id || typeof decision.label !== "string" || decision.choice_index !== null && decision.choice_index !== void 0 && (!Number.isSafeInteger(decision.choice_index) || decision.choice_index < 0) || Array.isArray(decision.selected_pattern_indices) && decision.selected_pattern_indices.length) continue;
		actions.push({
			id: `choice-${index}`,
			label: decision.label,
			behavior,
			optionId: decision.option_id,
			...decision.choice_index === null || decision.choice_index === void 0 ? {} : { choiceIndex: decision.choice_index }
		});
	}
	if (!actions.some((action) => action.behavior === "allow") || !actions.some((action) => action.behavior === "deny")) return null;
	return {
		id: approvalKey(session, row),
		approvalId: row.approval_id,
		turnId: row.turn_id,
		...row.subagent_id ? { subagentId: row.subagent_id } : {},
		actions,
		fingerprint: JSON.stringify([
			row.tool_name,
			row.display,
			row.raw_input,
			actions
		])
	};
}
function createConnection(capabilities, gateway = fromEnvironment()) {
	const listeners = /* @__PURE__ */ new Set();
	const sessions = /* @__PURE__ */ new Map();
	let closed = false;
	const emit = (event) => {
		for (const listener of listeners) listener(event);
	};
	function persistence(session) {
		const savedPending = (pending) => ({
			requestId: pending.requestId,
			...pending.nativeRequestId ? { nativeRequestId: pending.nativeRequestId } : {},
			...pending.queueEntryId !== void 0 ? { queueEntryId: pending.queueEntryId } : {},
			...pending.entryIndex !== void 0 ? { entryIndex: pending.entryIndex } : {},
			...pending.cancelRequested ? { cancelRequested: true } : {},
			clientMessageId: pending.clientMessageId,
			startIndex: pending.startIndex,
			instanceId: pending.instanceId,
			epoch: pending.epoch
		});
		return {
			version: 1,
			data: {
				gatewayId: session.gatewayId,
				targetId: gateway.targetId,
				threadId: session.threadId,
				...session.active ? { active: savedPending(session.active) } : {},
				...session.uncertain ? { uncertain: savedPending(session.uncertain) } : {}
			}
		};
	}
	function persist(session) {
		if (capabilities.includes("session.persistence")) emit({
			type: "session.persistence",
			sessionId: session.id,
			persistence: persistence(session)
		});
	}
	function accept(session, pending) {
		session.uncertain = null;
		session.active = pending;
		emit({
			type: "session.prompt_result",
			sessionId: session.id,
			clientMessageId: pending.clientMessageId,
			result: {
				type: "turn",
				turnId: pending.turnId
			}
		});
		emit({
			type: "session.turn",
			sessionId: session.id,
			turnId: pending.turnId,
			state: "started"
		});
		persist(session);
	}
	async function catalog(requestId) {
		const listed = await gateway.list();
		if (!listed || !Array.isArray(listed.threads) || typeof listed.instance_id !== "string" || typeof listed.epoch !== "string") throw new Error("Invalid ZedLink thread list");
		const models = listed.threads.filter((row) => row.agent?.kind === "zed" && typeof row.thread_id === "string" && typeof row.title === "string").map((row) => ({
			id: modelId(row.thread_id),
			label: `${row.title} · ${row.agent?.name ?? "Zed Agent"}`
		}));
		emit({
			type: "catalog",
			requestId,
			catalog: {
				models,
				modes: [],
				thinkingOptions: [],
				...models.length ? { defaultModel: models[0].id } : {}
			}
		});
	}
	async function syncNativeSettings(session) {
		if (typeof gateway.settings !== "function") return;
		let settings;
		try {
			settings = await gateway.settings(session.threadId, session.instanceId, session.epoch);
		} catch {
			return;
		}
		if (settings?.configuration_owner !== "zed") return;
		const modelName = settings.model?.name;
		const profile = settings.profile_id;
		if (typeof modelName === "string" && modelName) {
			const summary = JSON.stringify([modelName, profile]);
			if (summary !== session.lastNativeSettings) {
				session.lastNativeSettings = summary;
				emit({
					type: "session.notice",
					sessionId: session.id,
					notice: {
						id: "zedlink-native-model",
						severity: "info",
						title: `Zed model: ${modelName}`,
						description: typeof profile === "string" ? `Zed profile: ${profile}. Change the model or profile in Zed.` : "Change the model in Zed."
					}
				});
			}
		}
		const usage = settings.context_usage;
		if (usage && Number.isSafeInteger(usage.used_tokens) && Number.isSafeInteger(usage.max_tokens)) {
			const mapped = {
				contextWindowUsedTokens: usage.used_tokens,
				contextWindowMaxTokens: usage.max_tokens,
				...Number.isSafeInteger(usage.input_tokens) ? { inputTokens: usage.input_tokens } : {},
				...Number.isSafeInteger(usage.output_tokens) ? { outputTokens: usage.output_tokens } : {}
			};
			const fingerprint = JSON.stringify(mapped);
			if (fingerprint !== session.lastUsage) {
				session.lastUsage = fingerprint;
				emit({
					type: "session.usage",
					sessionId: session.id,
					usage: mapped
				});
			}
		}
	}
	function syncApprovals(session, snapshot) {
		if (!Array.isArray(snapshot.pending_approvals)) return;
		const rows = [...snapshot.pending_approvals];
		if (Array.isArray(snapshot.subagents)) {
			for (const child of snapshot.subagents) if (Array.isArray(child?.pending_approvals)) rows.push(...child.pending_approvals);
		}
		const present = /* @__PURE__ */ new Set();
		let unsupported = 0;
		for (const row of rows) {
			const approval = approvalFromNative(session, row);
			if (!approval || !capabilities.includes("permission")) {
				unsupported++;
				continue;
			}
			present.add(approval.id);
			if (session.approvals.get(approval.id)?.fingerprint === approval.fingerprint) continue;
			session.approvals.set(approval.id, approval);
			emit({
				type: "session.permission",
				sessionId: session.id,
				request: {
					id: approval.id,
					name: row.tool_name,
					kind: "tool",
					title: row.display || row.tool_name,
					description: "Review this native Zed tool request. These choices apply once.",
					input: row.raw_input,
					actions: approval.actions.map(({ id, label, behavior }) => ({
						id,
						label,
						behavior,
						variant: behavior === "deny" ? "secondary" : "primary"
					}))
				}
			});
		}
		for (const id of session.approvals.keys()) if (!present.has(id)) {
			session.approvals.delete(id);
			emit({
				type: "session.permission_resolved",
				sessionId: session.id,
				permissionId: id
			});
		}
		if (unsupported) emit({
			type: "session.notice",
			sessionId: session.id,
			notice: {
				id: `zedlink-approval:${session.epoch}:${session.threadId}`,
				severity: "warning",
				title: "Approval waiting in Zed",
				description: "Open Zed or ZedLink to review approval choices this plugin cannot present safely."
			}
		});
	}
	async function publish(session, snapshot) {
		if (!validPage(snapshot, session)) throw new Error("Invalid ZedLink transcript page");
		const start = snapshot.entry_start_index;
		let persistenceChanged = false;
		for (let offset = 0; offset < snapshot.entries_markdown.length; offset++) {
			const index = start + offset;
			const markdown = snapshot.entries_markdown[offset];
			const meta = snapshot.entries_meta?.[offset];
			const active = session.active;
			const exactEntry = active?.nativeRequestId && snapshot.active_request_id === active.nativeRequestId && Number.isSafeInteger(snapshot.active_request_entry_index) && snapshot.active_request_entry_index === index;
			const receiptEntry = active?.entryIndex === index;
			const fallbackEntry = active && snapshot.active_request_id == null && index >= active.startIndex && markdown.startsWith("## User\n") && markdown.replace(/^## User\n+/, "").trim() === active.text;
			const matchesPrompt = active && !active.matched && (exactEntry || receiptEntry || fallbackEntry);
			if (active && !active.matched && !matchesPrompt && index >= active.startIndex && markdown.startsWith("## User\n") && markdown.replace(/^## User\n+/, "").trim() === active.text) continue;
			const signature = JSON.stringify([markdown, meta ?? null]);
			if (session.seen.get(index) === signature && !matchesPrompt) continue;
			session.seen.set(index, signature);
			const clientId = matchesPrompt ? active.clientMessageId : void 0;
			if (matchesPrompt) {
				active.matched = true;
				active.promptIndex = index;
				active.entryIndex = index;
				persistenceChanged = true;
			}
			for (const item of parseEntry(markdown, `zed:${session.epoch}:${session.threadId}:${index}`, clientId, meta)) emit({
				type: "timeline.item",
				sessionId: session.id,
				item
			});
		}
		if (session.active?.nativeTurnId === void 0 && session.active?.nativeRequestId && snapshot.active_request_id === session.active.nativeRequestId && snapshot.status === "Generating" && Number.isSafeInteger(snapshot.current_turn_id) && snapshot.current_turn_id >= 0 && snapshot.current_turn_id <= 4294967295) {
			session.active.nativeTurnId = snapshot.current_turn_id;
			persistenceChanged = true;
		}
		const active = session.active;
		const hasReply = active?.matched && snapshot.entries_markdown.some((entry, offset) => start + offset > active.promptIndex && entry.startsWith("## Assistant\n"));
		if (active && snapshot.status === "Idle" && (active.cancelRequested || active.matched && (snapshot.had_error || hasReply))) {
			emit({
				type: "session.turn",
				sessionId: session.id,
				turnId: session.active.turnId,
				state: session.active.cancelRequested ? "canceled" : snapshot.had_error ? "failed" : "completed"
			});
			session.active = null;
			persistenceChanged = true;
		}
		if (persistenceChanged) persist(session);
		syncApprovals(session, snapshot);
		if (Number.isSafeInteger(snapshot.last_sequence) && snapshot.last_sequence >= 0) session.lastSequence = snapshot.last_sequence;
	}
	async function refresh(session) {
		if (session.closed || session.polling) return;
		session.polling = true;
		try {
			if (session.uncertain) if (session.uncertain.instanceId !== session.instanceId || session.uncertain.epoch !== session.epoch) emit({
				type: "session.notice",
				sessionId: session.id,
				notice: {
					id: "zedlink-stale-delivery",
					severity: "warning",
					title: "Message delivery still unknown",
					description: "Zed restarted before this request could be reconciled. Inspect the native thread; it will not be resent."
				}
			});
			else {
				const status = await gateway.status(session.instanceId, session.epoch, session.uncertain.requestId);
				if (status?.known === true) {
					if (typeof status.native_request_id === "string" && status.native_request_id) session.uncertain.nativeRequestId = status.native_request_id;
					if (Number.isSafeInteger(status.queue_entry_id) && status.queue_entry_id >= 0) session.uncertain.queueEntryId = status.queue_entry_id;
					if (Number.isSafeInteger(status.entry_index) && status.entry_index >= session.uncertain.startIndex) session.uncertain.entryIndex = status.entry_index;
					accept(session, session.uncertain);
				}
			}
			if (session.active && !session.active.matched) try {
				const active = session.active;
				const status = await gateway.status(session.instanceId, session.epoch, active.requestId);
				if (session.active === active && status?.known === true) if (status.outcome === "removed") {
					emit({
						type: "session.turn",
						sessionId: session.id,
						turnId: active.turnId,
						state: "canceled"
					});
					session.active = null;
					persist(session);
				} else {
					let changed = false;
					if (typeof status.native_request_id === "string" && status.native_request_id !== active.nativeRequestId) {
						active.nativeRequestId = status.native_request_id;
						changed = true;
					}
					if (Number.isSafeInteger(status.queue_entry_id) && status.queue_entry_id >= 0 && status.queue_entry_id !== active.queueEntryId) {
						active.queueEntryId = status.queue_entry_id;
						changed = true;
					}
					if (Number.isSafeInteger(status.entry_index) && status.entry_index >= active.startIndex && status.entry_index !== active.entryIndex) {
						active.entryIndex = status.entry_index;
						changed = true;
					}
					if (changed) persist(session);
				}
			} catch {}
			if (session.lastSequence !== null && typeof gateway.events === "function") try {
				const changes = await gateway.events(session.threadId, session.instanceId, session.epoch, session.lastSequence);
				if (changes?.instance_id !== session.instanceId || changes.epoch !== session.epoch || changes.thread_id !== session.threadId || !Number.isSafeInteger(changes.last_sequence) || changes.last_sequence < session.lastSequence || !Array.isArray(changes.events)) throw new Error("Invalid ZedLink event cursor");
				if (changes.last_sequence === session.lastSequence && !session.active && !session.uncertain) return;
			} catch (error) {
				if (!(error instanceof Error && "code" in error && error.code === "RESYNC_REQUIRED")) throw error;
				session.lastSequence = null;
			}
			const snapshot = await gateway.snapshot(session.threadId, session.instanceId, session.epoch);
			const settingsMayHaveChanged = snapshot.last_sequence !== session.lastSequence;
			if (!session.closed && session.active && !session.active.matched && snapshot.entry_start_index > session.active.startIndex) {
				const missing = await gateway.history(session.threadId, session.instanceId, session.epoch, snapshot.entry_start_index);
				if (missing?.entry_end_index === snapshot.entry_start_index && missing.entry_start_index <= session.active.startIndex) await publish(session, missing);
			}
			if (!session.closed) await publish(session, snapshot);
			if (!session.closed && settingsMayHaveChanged) await syncNativeSettings(session);
		} catch (error) {
			emit({
				type: "session.notice",
				sessionId: session.id,
				notice: {
					id: "zedlink-connection",
					severity: "warning",
					title: "ZedLink unavailable",
					description: error instanceof Error ? error.message : "Refresh failed"
				}
			});
		} finally {
			session.polling = false;
			if (!session.closed) session.timer = setTimeout(() => {
				refresh(session);
			}, session.active ? 350 : 1500);
		}
	}
	async function open(input) {
		if (!capabilities.includes("prompt.message")) throw new Error("Paseo does not support message prompts for this provider");
		const selected = threadId(input.config?.model);
		const gatewayId = await gateway.identity();
		const listed = await gateway.list();
		const found = listed?.threads?.find((row) => row.thread_id === selected && row.agent?.kind === "zed");
		if (!found) throw new Error("This Zed thread is no longer exposed");
		const persisted = input.persistence?.data;
		if (persisted && (persisted.gatewayId !== gatewayId || persisted.targetId !== gateway.targetId || persisted.threadId !== selected)) throw new Error("Saved Paseo session belongs to another ZedLink gateway, target, or thread");
		const restoredActive = persisted?.active ? restorePending(persisted.active) : null;
		const restoredUncertain = persisted?.uncertain ? restorePending(persisted.uncertain) : null;
		if (restoredActive && restoredUncertain) throw new Error("Saved ZedLink receipt has conflicting turns");
		const activeIsCurrent = restoredActive?.instanceId === listed.instance_id && restoredActive?.epoch === listed.epoch;
		const session = {
			id: input.sessionId,
			threadId: selected,
			instanceId: listed.instance_id,
			epoch: listed.epoch,
			gatewayId,
			modelId: input.config.model,
			modelLabel: found.title,
			seen: /* @__PURE__ */ new Map(),
			approvals: /* @__PURE__ */ new Map(),
			active: activeIsCurrent ? restoredActive : null,
			uncertain: restoredUncertain,
			submitting: false,
			timer: null,
			closed: false,
			polling: false,
			lastSequence: null,
			lastNativeSettings: null,
			lastUsage: null
		};
		const snapshot = await gateway.snapshot(selected, session.instanceId, session.epoch);
		if (!validPage(snapshot, session)) throw new Error("Invalid ZedLink transcript page");
		if (Number.isSafeInteger(snapshot.last_sequence) && snapshot.last_sequence >= 0) session.lastSequence = snapshot.last_sequence;
		const pages = [snapshot];
		let before = snapshot.entry_start_index;
		if (input.history !== "skip") for (let page = 0; before > 0 && page < 16; page++) {
			const older = await gateway.history(selected, session.instanceId, session.epoch, before);
			if (!validPage(older, session) || older.entry_end_index !== before || older.entry_start_index === before) throw new Error("ZedLink history is not contiguous");
			pages.unshift(older);
			before = older.entry_start_index;
		}
		sessions.set(session.id, session);
		emit({
			type: "session.opened",
			requestId: input.requestId,
			sessionId: session.id,
			capabilities,
			restoration: "core",
			cwd: input.config.cwd,
			...capabilities.includes("session.persistence") ? { persistence: persistence(session) } : {}
		});
		emit({
			type: "session.config",
			sessionId: session.id,
			config: {
				model: session.modelId,
				modes: [],
				thinkingOptions: [],
				models: [{
					id: session.modelId,
					label: session.modelLabel
				}],
				settings: []
			}
		});
		await syncNativeSettings(session);
		if (session.active) emit({
			type: "session.turn",
			sessionId: session.id,
			turnId: session.active.turnId,
			state: "started"
		});
		if (restoredActive && !activeIsCurrent) emit({
			type: "session.notice",
			sessionId: session.id,
			notice: {
				id: "zedlink-previous-instance",
				severity: "warning",
				title: "Previous Zed run unavailable",
				description: "Zed restarted; the earlier request cannot be canceled or replayed from this instance."
			}
		});
		if (input.history === "skip") snapshot.entries_markdown?.forEach((entry, offset) => session.seen.set(snapshot.entry_start_index + offset, JSON.stringify([entry, snapshot.entries_meta?.[offset] ?? null])));
		else {
			for (const page of pages) await publish(session, page);
			if (before > 0) emit({
				type: "session.notice",
				sessionId: session.id,
				notice: {
					id: "zedlink-history-truncated",
					severity: "info",
					title: "Older Zed history is not loaded",
					description: "Open the native Zed or ZedLink view for the complete conversation."
				}
			});
		}
		emit({
			type: "session.ready",
			requestId: input.requestId,
			sessionId: session.id
		});
		refresh(session);
	}
	async function prompt(input) {
		const session = sessions.get(input.sessionId);
		const messageId = input.prompt?.clientMessageId;
		const fail = (message) => emit({
			type: "session.prompt_result",
			sessionId: input.sessionId,
			clientMessageId: messageId,
			result: {
				type: "failed",
				error: { message }
			}
		});
		if (!session || session.closed) return fail("ZedLink session is unavailable");
		if (!messageId || input.prompt?.delivery === "steer" || input.prompt?.input?.type !== "message") return fail("Only new text messages are supported by this ZedLink plugin");
		const parts = input.prompt.input.content;
		if (!Array.isArray(parts) || !parts.length || !parts.every((part) => part.type === "text" && typeof part.text === "string")) return fail("Only text is supported by this ZedLink plugin");
		if (session.uncertain) return fail("Previous message delivery is still uncertain; check ZedLink before sending another message");
		if (session.active || session.submitting) return fail("Wait for the current Zed turn to finish");
		const text = parts.map((part) => part.text).join("\n").trim();
		if (!text) return fail("The message is empty");
		const requestId = randomUUID();
		const turnId = `zedlink:${requestId}`;
		session.submitting = true;
		try {
			let before;
			try {
				before = await gateway.snapshot(session.threadId, session.instanceId, session.epoch);
			} catch {
				return fail("ZedLink is unavailable before message submission");
			}
			if (!validPage(before, session)) return fail("ZedLink thread changed before message submission");
			let known = false;
			let nativeRequestId;
			let queueEntryId;
			let entryIndex;
			try {
				const receipt = await gateway.send(session.threadId, session.instanceId, session.epoch, text, requestId);
				known = receipt != null && receipt.outcome !== "unknown";
				if (typeof receipt?.native_request_id === "string" && receipt.native_request_id) nativeRequestId = receipt.native_request_id;
				if (Number.isSafeInteger(receipt?.queue_entry_id) && receipt.queue_entry_id >= 0) queueEntryId = receipt.queue_entry_id;
				if (Number.isSafeInteger(receipt?.entry_index) && receipt.entry_index >= before.entry_end_index) entryIndex = receipt.entry_index;
			} catch {}
			if (!known) try {
				const status = await gateway.status(session.instanceId, session.epoch, requestId);
				known = status?.known === true;
				if (typeof status?.native_request_id === "string" && status.native_request_id) nativeRequestId = status.native_request_id;
				if (Number.isSafeInteger(status?.queue_entry_id) && status.queue_entry_id >= 0) queueEntryId = status.queue_entry_id;
				if (Number.isSafeInteger(status?.entry_index) && status.entry_index >= before.entry_end_index) entryIndex = status.entry_index;
			} catch {}
			const pending = {
				turnId,
				clientMessageId: messageId,
				requestId,
				nativeRequestId,
				queueEntryId,
				entryIndex,
				startIndex: before.entry_end_index,
				instanceId: session.instanceId,
				epoch: session.epoch,
				text,
				matched: false,
				cancelRequested: false
			};
			if (known) accept(session, pending);
			else {
				session.uncertain = pending;
				persist(session);
				emit({
					type: "session.notice",
					sessionId: session.id,
					notice: {
						id: "zedlink-delivery-unknown",
						severity: "warning",
						title: "Message delivery unknown",
						description: "ZedLink has not confirmed this request. Check the native thread; the plugin will not resend it."
					}
				});
			}
			refresh(session);
		} finally {
			session.submitting = false;
		}
	}
	async function interrupt(input) {
		traceStop("stop.received");
		const session = sessions.get(input.sessionId);
		if (!session || session.closed || !session.active) throw new Error("No active ZedLink turn to stop");
		const active = session.active;
		if (active.queueEntryId !== void 0 && typeof gateway.removeQueued === "function") {
			let outcome;
			try {
				outcome = (await gateway.removeQueued(session.threadId, session.instanceId, session.epoch, active.requestId, active.queueEntryId))?.outcome;
			} catch (error) {
				if (error && typeof error === "object" && "code" in error && error.code === "UNSUPPORTED_CAPABILITY") outcome = "not_queued";
				else try {
					const status = await gateway.status(session.instanceId, session.epoch, active.requestId);
					if (status?.known === true) outcome = status.outcome;
				} catch {}
			}
			if (outcome === "removed") {
				if (session.active !== active) throw new Error("The Paseo turn changed during Stop");
				session.active = null;
				emit({
					type: "session.turn",
					sessionId: session.id,
					turnId: active.turnId,
					state: "canceled"
				});
				persist(session);
				emit({
					type: "request.completed",
					requestId: input.requestId
				});
				return;
			}
			if (outcome !== "not_queued") throw new Error("Queued ZedLink removal was not confirmed; Stop was not acknowledged");
		}
		const snapshot = await gateway.snapshot(session.threadId, session.instanceId, session.epoch);
		if (!validPage(snapshot, session) || snapshot.status !== "Generating") throw new Error("The native Zed turn is no longer running; Stop was not sent");
		await publish(session, snapshot);
		if (session.active !== active || !active.nativeRequestId || snapshot.active_request_id !== active.nativeRequestId) throw new Error("The phone request is not the current native Zed turn; Stop was not sent");
		if (!Number.isSafeInteger(active.nativeTurnId)) throw new Error("The native Zed turn has not been identified yet; Stop is unavailable");
		if (snapshot.current_turn_id !== active.nativeTurnId) throw new Error("The native Zed turn changed; Stop was not sent");
		if ((await gateway.cancel(session.threadId, session.instanceId, session.epoch, active.nativeTurnId))?.outcome !== "requested") throw new Error("ZedLink did not confirm the native cancellation request");
		traceStop("stop.native_requested");
		active.cancelRequested = true;
		persist(session);
		emit({
			type: "request.completed",
			requestId: input.requestId
		});
		refresh(session);
	}
	async function permission(input) {
		const session = sessions.get(input.sessionId);
		if (!session || session.closed || !capabilities.includes("permission")) throw new Error("ZedLink approval is unavailable");
		const fail = (message) => {
			emit({
				type: "session.notice",
				sessionId: session.id,
				notice: {
					id: `zedlink-approval-response:${input.permissionId}`,
					severity: "warning",
					title: "Approval not sent",
					description: message
				}
			});
			const error = new Error(message);
			error.name = "ZedLinkApprovalNotSent";
			throw error;
		};
		const approval = session.approvals.get(input.permissionId);
		const response = input.response;
		const matching = approval?.actions.filter((candidate) => candidate.behavior === response?.behavior) ?? [];
		const action = response?.selectedActionId === void 0 ? matching.length === 1 ? matching[0] : void 0 : matching.find((candidate) => candidate.id === response.selectedActionId);
		if (!approval || !action || response.updatedInput !== void 0 || response.updatedPermissions !== void 0 || response.interrupt === true || response.message !== void 0 && (response.behavior !== "deny" || typeof response.message !== "string")) return fail("Choose one of the current one-time native approval options.");
		try {
			const row = (await gateway.approvals(session.threadId, session.instanceId, session.epoch))?.approvals?.find((candidate) => approvalKey(session, candidate) === approval.id);
			const fresh = approvalFromNative(session, row);
			const exact = fresh?.actions.find((candidate) => candidate.id === action.id && candidate.optionId === action.optionId && candidate.choiceIndex === action.choiceIndex && candidate.behavior === action.behavior);
			if (!fresh || fresh.fingerprint !== approval.fingerprint || !exact) return fail("The native approval changed or expired. Refresh before deciding.");
			if ((await gateway.respondApproval(session.threadId, session.instanceId, session.epoch, approval.approvalId, approval.turnId, action.optionId, action.choiceIndex, approval.subagentId))?.outcome !== "resolved") return fail("ZedLink did not confirm the approval decision.");
			session.approvals.delete(approval.id);
			emit({
				type: "session.permission_resolved",
				sessionId: session.id,
				permissionId: approval.id
			});
			refresh(session);
		} catch (error) {
			if (error instanceof Error && error.name === "ZedLinkApprovalNotSent") throw error;
			fail("ZedLink did not confirm this decision. Check the native approval before acting again.");
		}
	}
	return {
		version: 1,
		capabilities,
		onEvent(listener) {
			listeners.add(listener);
			return () => {
				listeners.delete(listener);
			};
		},
		async send(input) {
			if (closed) throw new Error("ZedLink provider is closed");
			switch (input.type) {
				case "catalog": return catalog(input.requestId);
				case "session.open": return open(input);
				case "session.prompt": return prompt(input);
				case "session.interrupt": return interrupt(input);
				case "session.permission": return permission(input);
				case "session.close": {
					const session = sessions.get(input.sessionId);
					if (session) {
						session.closed = true;
						if (session.timer) clearTimeout(session.timer);
						sessions.delete(session.id);
					}
					emit({
						type: "session.closed",
						sessionId: input.sessionId
					});
					emit({
						type: "request.completed",
						requestId: input.requestId
					});
					return;
				}
				default: throw new Error(`Unsupported ZedLink provider input: ${input.type}`);
			}
		},
		async close() {
			closed = true;
			for (const session of sessions.values()) {
				session.closed = true;
				if (session.timer) clearTimeout(session.timer);
			}
			sessions.clear();
			listeners.clear();
		}
	};
}
//#endregion
export { GatewayClient, GatewayError, createConnection, modelId, threadId };
