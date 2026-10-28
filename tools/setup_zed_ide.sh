#!/usr/bin/env bash
set -euo pipefail

zedlink_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
skip_build=false
skip_config=false
skip_tasks=false
accept_defaults=false
remove_tasks=false
tasks_file=""

usage() {
  cat <<'TEXT'
Usage: bash tools/setup_zed_ide.sh [options]

Guided Linux and macOS setup for the patched ZedLink build and Zed IDE tasks.

  --yes                  Accept the safe defaults
  --skip-build           Do not build patched Zed or the gateway
  --skip-config          Do not change ZedLink connection settings
  --skip-global-tasks    Do not install tasks into Zed's global task picker
  --tasks-file PATH      Use another tasks.json (primarily for testing)
  --remove-global-tasks  Remove only ZedLink entries from global tasks.json
  -h, --help             Show this help
TEXT
}

while (($#)); do
  case "$1" in
    --yes) accept_defaults=true ;;
    --skip-build) skip_build=true ;;
    --skip-config) skip_config=true ;;
    --skip-global-tasks) skip_tasks=true ;;
    --remove-global-tasks) remove_tasks=true ;;
    --tasks-file)
      shift
      [[ $# -gt 0 ]] || { printf '%s\n' '--tasks-file requires a path' >&2; exit 2; }
      tasks_file="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

task_arguments=()
if [[ -n "$tasks_file" ]]; then
  task_arguments+=(--tasks-file "$tasks_file")
fi

if $remove_tasks; then
  python3 "$zedlink_root/tools/zed_task_installer.py" remove "${task_arguments[@]}"
  exit 0
fi

ask() {
  local prompt="$1"
  local default_answer="$2"
  local answer
  if $accept_defaults; then
    [[ "$default_answer" == "yes" ]]
    return
  fi
  if [[ "$default_answer" == "yes" ]]; then
    read -r -p "$prompt [Y/n] " answer
    [[ -z "$answer" || "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
  else
    read -r -p "$prompt [y/N] " answer
    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
  fi
}

printf '\nZedLink guided setup\n'
printf 'Repository: %s\n\n' "$zedlink_root"

for command in python3 git cargo rustup; do
  command -v "$command" >/dev/null || {
    printf 'Missing required command: %s\n' "$command" >&2
    exit 1
  }
done

if ! python3 -c 'import qrcode' >/dev/null 2>&1; then
  printf 'Note: Python qrcode is missing. Build and configuration can continue, but Pair a device will need it.\n'
  printf 'Install the qrcode package (your Linux distribution, or pip on macOS) before pairing.\n\n'
fi

if ! $skip_build; then
  build_default=yes
  if [[ -x "$zedlink_root/zed-source/target/debug/zed" && -x "$zedlink_root/gateway/target/debug/zedlink-gateway" ]]; then
    build_default=no
  fi
  if ask "Build or update patched Zed and the gateway?" "$build_default"; then
    bash "$zedlink_root/tools/install_linux.sh"
  else
    printf 'Skipped build.\n'
  fi
fi

if ! $skip_config; then
  config_base="${XDG_CONFIG_HOME:-$HOME/.config}"
  config_file="$config_base/zedlink/config.json"
  config_default=yes
  [[ -f "$config_file" ]] && config_default=no
  if ask "Configure the project, private address, and TLS certificate now?" "$config_default"; then
    python3 "$zedlink_root/tools/zedlink_manager.py" configure
  else
    printf 'Kept existing configuration.\n'
  fi
fi

if ! $skip_tasks; then
  if ask "Install ZedLink commands in Zed's global task picker?" yes; then
    python3 "$zedlink_root/tools/zed_task_installer.py" install "${task_arguments[@]}"
  else
    printf 'Skipped global Zed tasks. Project tasks remain available in this repository.\n'
  fi
fi

config_base="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ -f "$config_base/zedlink/config.json" ]]; then
  python3 "$zedlink_root/tools/zedlink_manager.py" install-launcher
  python3 "$zedlink_root/tools/zedlink_manager.py" install-cli
fi

cat <<'TEXT'

Setup finished.

Next steps in Zed:
  1. Press Ctrl+Shift+P, type "task: spawn", and select it.
  2. Run "ZedLink: Status". If it says not configured, run "ZedLink: Configure".
  3. Open "ZedLink — Patched Zed" from the application menu and confirm your normal model is selected.
  4. In that patched window, open the native Agent thread you want to access remotely.
  5. Type /remote-control in the Agent composer and select "Remote Control".
  6. Run "ZedLink: Start gateway" and leave its task terminal running.
  7. Run "ZedLink: Pair a device". Click the private link for this computer or scan the QR from another device.

Expected Zed message after step 5:
  Thread exposed to ZedLink locally.

If /remote-control is missing, you are in ordinary Zed rather than the patched window.
The complete first-time walkthrough is in README.md.

ZedLink uses the model, tools, MCP servers, and permissions of that patched Zed window.
It does not install a stock Zed extension or create a second model client.
TEXT
