# End-to-end test and release contract

Status: specification only. No application tests have been run by the author of this handoff package.

## Evidence hierarchy

| Layer | Proves | Does not prove |
| --- | --- | --- |
| Protocol unit tests | Serialization, reducers, recovery rules | Native integration |
| Gateway fixture integration | Auth, transport, pairing, limits | Real thread control |
| Real Zed + deterministic local model | Native execution, tools, approvals, shared state | Actual model quality or physical phone behavior |
| Real Zed + real local LLM | Actual configured provider/task outcome | Every deterministic race condition |
| Simulator + real gateway/Zed | iOS UI/transport integration | Physical networking/signing |
| Physical iPhone + real stack | Product round trip and reconnect experience | Untested versions/platforms |

All release claims must name the layer executed. Mocks and screenshots alone are insufficient.

## Disposable fixture project

Create this project in an isolated test directory, not the user's production workspace. Initialize a temporary Git repository and commit the baseline so diffs are meaningful.

`calculator.py`:

```python
def add(a, b):
    return a - b
```

`test_calculator.py`:

```python
import unittest
from calculator import add

class CalculatorTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative(self):
        self.assertEqual(add(-2, -3), -5)

    def test_mixed(self):
        self.assertEqual(add(-2, 3), 1)

if __name__ == '__main__':
    unittest.main()
```

Baseline and post-repair command:

```bash
python3 -m unittest -v
```

Baseline must fail; after the repair it must pass. Add a harmless `approval_sentinel.txt` operation only to the deterministic approval fixture. Do not depend on a probabilistic model choosing the exact operation required for a permissions test.

## Deterministic local model fixture

Implement a loopback-only model endpoint compatible with the actual provider/API shape used by the pinned Zed build. Discover model-list, streaming, tool-call, and request semantics from source and real sanitized requests. Do not assume all providers use the same format.

Script scenarios for a streamed answer, file read, file edit, permission-gated sentinel operation, failure, and delayed response. Record safe counters and test IDs. Do not log real credentials or full prompts from other sessions.

Run through Zed's real provider and native agent paths. Tool-call fixtures must produce actual native tool requests, not fabricated gateway events.

## Test matrix

| ID | Scenario | Required assertion |
| --- | --- | --- |
| Z01 | Desktop creates thread | Bridge identifies same native thread and instance |
| Z02 | Remote submits prompt | Desktop transcript contains one matching user message/native turn |
| Z03 | Assistant streams | Desktop and client converge to same final content |
| Z04 | File read/edit | Actual native tool state and expected filesystem effects |
| Z05 | Deny pending operation | Sentinel effect absent; authoritative approval denied |
| Z06 | Approve pending operation | Only the exact pending effect occurs |
| Z07 | Desktop/mobile approval race | One decision wins; other is already resolved |
| Z08 | Expired approval replay | No new operation authorized |
| Z09 | Cancel delayed turn | Correct native turn cancelled; later turn unaffected |
| Z10 | Concurrent desktop/mobile prompts | Native queue semantics; no dropped or duplicated submissions |
| Z11 | Desktop edits message | Client resyncs or correctly maps edit |
| R01 | Disconnect while streaming | Replay/snapshot restores authoritative content |
| R02 | Acceptance before disconnect | Same request retry adds no second prompt |
| R03 | Same request ID, altered payload | Conflict; no extra execution |
| R04 | Replay history exhausted | Fresh snapshot; no duplicated text |
| R05 | Snapshot during event activity | No state/event gap or double application |
| R06 | Gateway restarts | Zed continues; pending request status reconciles |
| R07 | Zed restarts | New instance/epoch; uncertain delivery not blindly resent |
| R08 | Multiple instances/threads | Commands and events remain correctly scoped |
| A01 | Unpaired client | No thread metadata, stream, or execution access |
| A02 | Pairing expiry/reuse/brute retries | Expired/reused secret rejected; rate limits enforced |
| A03 | Revoke active device | Existing stream closes and future requests fail |
| A04 | Invalid TLS identity | Client refuses connection without insecure fallback |
| A05 | Hidden project/thread | No discovery or execution access |
| A06 | Malformed/oversized message | Bounded rejection; server remains healthy |
| A07 | Slow consumer | Bounded memory; resync/disconnect instead of unlimited queue |
| A08 | Diff path escape | Traversal/symlink escape rejected |
| A09 | Diagnostics | No credentials, private transcript, or hidden paths in logs |
| I01 | Simulator happy path | Actual gateway/Zed prompt round trip |
| I02 | Simulator request timeout | Delivery unknown handled without duplicate prompt |
| I03 | Simulator accessibility | Core actions accessible with large text/VoiceOver |
| P01 | Physical Wi-Fi | Existing desktop thread controlled from phone |
| P02 | Physical cellular/Tailscale | Same-thread round trip off local Wi-Fi |
| P03 | Wi-Fi/cellular transition | Reconnect without duplicated requests/messages |
| P04 | Background and return | State reconciled; no false continuous-connectivity claim |
| L01 | Actual local LLM task | Repair fixture, expected diff, passing unittest |
| L02 | Provider origin | Model requests originate from Zed only |

## Step-by-step physical happy path

1. Build/start the instrumented Zed version and gateway with isolated configuration.
2. Enable remote exposure for only the disposable project.
3. Open fixture project in desktop Zed and create a native thread.
4. Record native instance/thread IDs and baseline failing tests.
5. Configure the actual local model using Zed's normal settings. Phone/gateway receive no model key.
6. Pair the iPhone against a verified server identity over the private connection.
7. Open the same thread on the phone and ask: “Explain calculator.py without modifying files.”
8. Assert one user message in the authoritative thread and matching response on both screens.
9. Ask: “Fix add so it adds its arguments, then run the existing unittest suite.”
10. Verify matching native tool events, resulting diff, and passing tests. If a permission prompt appears, resolve it through the phone and verify desktop convergence.
11. Send a follow-up from desktop and observe it on the phone.
12. Confirm with controlled instrumentation that neither phone nor gateway directly called the model.
13. Repeat after switching to cellular/Tailscale, then disconnect/background and return.
14. Save sanitized evidence, exact commands/build identities, and assertions in VALIDATION_REPORT.md.

For permission guarantees use deterministic Z05–Z08 even if the actual-model happy path has no permission request. A missing permission request does not count as a passed approval test.

## Release gates

- Real native-thread proof passed.
- Deterministic permissions/idempotency/replay cases passed.
- Auth, TLS, exposure, revocation, and limits passed.
- Simulator integration passed against real gateway/Zed.
- Physical Wi-Fi/cellular happy path and reconnect checks passed.
- Actual local-model fixture repaired with matching state and passing tests.
- Compatibility and unresolved risks documented.

If any prerequisite is unavailable, mark its gate BLOCKED/NOT RUN. Deliver partial implementation honestly; do not label release ready.

## Automation and commands

Codex must discover actual build targets/schemes, implement repeatable scripts, and replace intended commands with verified ones in the validation report. Suggested script responsibilities include build adapter/gateway, run unit tests, launch isolated integration stack, execute deterministic scenarios, and run simulator tests. These are responsibilities, not existing scripts.

## Revision 2 — Connection and interface acceptance

Run the shared-thread tests over each available actual profile. Core required routes are Tailscale and WireGuard; other VPN/custom proxy claims require their own observed evidence. NOT RUN is required when infrastructure is unavailable.

| ID | Scenario | Required assertion |
| --- | --- | --- |
| N01 | Tailscale private endpoint | Physical phone reaches same gateway/native thread; TLS/auth intact |
| N02 | WireGuard private endpoint | Physical tunnel routes/DNS reach bridge without Tailscale dependency |
| N03 | Other routed VPN | Generic HTTPS path works; exact tested provider/version recorded |
| N04 | Local HTTPS | Local permission/route/trust works; no global TLS exception |
| N05 | Custom HTTPS proxy/tunnel | WSS streams, auth, prefix/timeout support verified; trust boundary documented |
| N06 | Provider switch during a turn | Same thread; uncertain requests reconciled; no duplicate messages |
| N07 | VPN disabled or missing route | Plain-language unreachable state; no false “VPN off” diagnosis |
| N08 | DNS failure / IP-only certificate mismatch | Distinct actionable errors; no TLS bypass |
| N09 | Server identity changes | Credentials not forwarded; trust/pairing review required |
| N10 | Endpoint redirect to other origin | No credential disclosure or automatic cross-origin replay |
| N11 | Alternate endpoint policy | No silent private-to-public failover; verified same gateway |
| N12 | External provider app unavailable | Manual instructions; no fabricated URL scheme |
| N13 | Gateway/proxy idle timeout | Bounded retry and replay; correct stale/live state |
| U01 | Guided onboarding | Add/test/pair profile and select thread without advanced fields |
| U02 | Small/large device, keyboard, landscape | Composer/approval controls remain usable |
| U03 | Light/dark, large type, VoiceOver | Contrast, labels, navigation, and targets remain accessible |
| U04 | Long code/tool text and diffs | Readable full decisive arguments; stable scroll; no clipping |
| U05 | Reduced motion/transparency | Native fallbacks without lost information |
| U06 | Fast profile edits/switches | Obsolete connection tasks cancel; no state/credential mixing |

Record real route setup, endpoint trust strategy, physical device/OS, and the tested service versions. Generic transport fixtures cannot establish provider compatibility. Network path monitoring alone cannot establish the active VPN identity.
