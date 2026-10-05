#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pinned_zed_revision="76659a55a8c10ed355a070f8764a0b1733e3c115"

actual_revision="$(git -C "$project_root/zed-source" rev-parse HEAD)"
if [[ "$actual_revision" != "$pinned_zed_revision" ]] &&
  ! git -C "$project_root/zed-source" merge-base --is-ancestor "$pinned_zed_revision" "$actual_revision"; then
  printf 'Expected Zed revision %s or a ZedLink fork branch based on it; got %s\n' \
    "$pinned_zed_revision" "$actual_revision" >&2
  exit 1
fi

RUSTUP_TOOLCHAIN=stable cargo fmt --manifest-path "$project_root/zed-source/Cargo.toml" \
  --package acp_thread --package agent --package agent_ui -- --check
RUSTUP_TOOLCHAIN=stable cargo check --manifest-path "$project_root/zed-source/Cargo.toml" \
  -p agent_ui --offline
git -C "$project_root/zed-source" apply --reverse --check \
  "$project_root/patches/zed-1.22.0-local-probe.patch"

cargo test --manifest-path "$project_root/protocol-core/Cargo.toml" --offline
cargo fmt --manifest-path "$project_root/gateway/Cargo.toml" -- --check
cargo check --manifest-path "$project_root/gateway/Cargo.toml" --offline
node --check "$project_root/gateway/web/app.js"
python3 -m json.tool "$project_root/.zed/tasks.json" >/dev/null
bash -n "$project_root/tools/install_linux.sh"
bash -n "$project_root/tools/setup_zed_ide.sh"
python3 -m py_compile "$project_root/tools/zedlink_probe_client.py" \
  "$project_root/tools/zedlink_gateway_client.py" \
  "$project_root/tools/test_gateway_transport.py" \
  "$project_root/tools/test_tailnet_bind.py" \
  "$project_root/tools/test_moshi_discovery.py" \
  "$project_root/tools/test_native_fixture.py" \
  "$project_root/tools/test_native_cancel.py" \
  "$project_root/tools/test_native_gateway_cancel.py" \
  "$project_root/tools/test_real_browser_cancel.py" \
  "$project_root/tools/test_native_browser_commands.py" \
  "$project_root/tools/pair_phone.py" \
  "$project_root/tools/zedlink_manager.py" \
  "$project_root/tools/zed_task_installer.py" \
  "$project_root/tools/deterministic_model_fixture.py"
printf 'Linux checks passed. Gateway transport integration requires tools/test_gateway_transport.py with loopback access.\n'
