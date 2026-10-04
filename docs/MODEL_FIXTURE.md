# Deterministic local model fixture

Status: the loopback HTTP fixture passes its own streaming-format check. It has **not yet** passed a prompt through a live native Zed Agent thread. It is for disposable projects and isolated Zed profiles only.

The pinned Zed source uses `crates/open_ai/src/open_ai.rs::stream_chat_completion` for custom models with Chat Completions enabled. It POSTs to `{api_url}/chat/completions` and reads `data:` SSE chunks through `[DONE]`. The isolated test profile's custom OpenAI model uses that default capability. [The fixture](../tools/deterministic_model_fixture.py) implements that route on `127.0.0.1`, returns controlled text chunks for `ZEDLINK_FIXTURE_STREAM` and `ZEDLINK_FIXTURE_DELAY`, and exposes only case counters at `/fixture/counters`. It does not log prompts, tool arguments, or credentials.

Run the fixture with a free local port and the disposable project root for its fixed approval sentinel:

```sh
python3 tools/deterministic_model_fixture.py --port 54259 --project-root /tmp/zedlink-fixture.KvjUfz
```

An isolated Zed settings file may point `language_models.openai.api_url` to `http://127.0.0.1:54259/v1`, add custom model `zedlink-fixture` to `available_models`, and set `agent.default_model` to that model. The test process used `OPENAI_API_KEY=zedlink-fixture-only`, a dummy value. Its copied disposable profile now sets `agent.tool_permissions.default` to `confirm` for later approval testing and disables other agent servers. Do not change the production Zed profile or replace its model credentials. The fixture's model ID must match the settings entry exactly.

On 2026-10-04, the SSE framing, concatenated final text, and case counter passed a direct loopback request. A separate copy of the earlier disposable Zed profile was configured for this fixture and launched with the patched binary, its own user-data directory, and private native probe. The live native-thread step is pending desktop selection of `/remote-control` in that separate window. Until that happens, fixture counters are **not** evidence of Zed execution.

When exactly one idle disposable native thread is exposed, run `python3 tools/test_native_fixture.py --socket /tmp/zedlink-deterministic-profile/probe/zedlink.sock`. The script reads the current instance and thread, checks a complete baseline snapshot, sends one unique `ZEDLINK_FIXTURE_STREAM` prompt, retries its same request ID, then checks the native event feed, one matching user and assistant entry, and the model fixture's case counter. It prints IDs and counts, never the prompt or transcript. It refuses to send if zero or multiple threads are exposed. The preflight on 2026-10-04 exited 3 with `NOT RUN: expected exactly one explicitly exposed native thread, found 0; no prompt sent`.

The fixture covers text streaming, a delayed text response, and one fixed `terminal` tool call for `ZEDLINK_FIXTURE_APPROVAL`. The tool call would write only `approval_sentinel.txt` in the configured disposable root after Zed grants permission. A direct HTTP check validated the tool-call and follow-up SSE shape without executing it. Denial, approval, desktop/mobile races, file edit, and failure scenarios remain unverified through real Zed. The fixture also exposes only sanitized tool names and schema property names at `/fixture/tools` to help check the native tool shape.
