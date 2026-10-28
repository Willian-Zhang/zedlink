#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="$project_root/zed-source"
patch="$project_root/patches/zed-native-agent-remote-control.patch"
pinned_revision="544780422affd11699fb531c49af5cc6e82a3fd7"
zed_upstream="https://github.com/zed-industries/zed.git"

if [[ ! -d "$source_root/.git" ]]; then
  if [[ -e "$source_root" ]]; then
    printf 'Refusing to replace existing non-Git path: %s\n' "$source_root" >&2
    exit 1
  fi
  git clone "$zed_upstream" "$source_root"
  git -C "$source_root" checkout --detach "$pinned_revision"
fi

actual_revision="$(git -C "$source_root" rev-parse HEAD)"
if [[ "$actual_revision" != "$pinned_revision" ]] &&
  ! git -C "$source_root" merge-base --is-ancestor "$pinned_revision" "$actual_revision"; then
  printf 'Expected Zed revision %s or a ZedLink branch based on it; found %s. No changes made.\n' \
    "$pinned_revision" "$actual_revision" >&2
  exit 1
fi

if git -C "$source_root" apply --reverse --check "$patch"; then
  printf 'ZedLink source patch is already applied.\n'
elif git -C "$source_root" apply --check "$patch"; then
  git -C "$source_root" apply "$patch"
  printf 'Applied pinned ZedLink source patch.\n'
else
  printf 'Patch cannot be applied cleanly; inspect zed-source before building.\n' >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  # rustup may default to an x86_64 host on Apple silicon, and "stable" may be older
  # than Zed requires, so build with Zed's pinned toolchain for the native architecture.
  channel="$(sed -n 's/^channel = "\(.*\)"/\1/p' "$source_root/rust-toolchain.toml")"
  arch="$(uname -m)"
  [[ "$arch" == "arm64" ]] && arch="aarch64"
  toolchain="$channel-$arch-apple-darwin"
  rustup toolchain install "$toolchain" --profile minimal --no-self-update
  features=()
  if ! xcrun -sdk macosx metal --version >/dev/null 2>&1; then
    printf 'Metal Toolchain not installed; compiling shaders at runtime instead.\n'
    features=(--features gpui_platform/runtime_shaders)
  fi
  # The pinned patch sets RELEASE_CHANNEL to stable. Build an optimized Nightly instead so
  # patched Zed never shares the official Zed's single-instance port or Stable database,
  # and still keeps credentials in the Keychain (Dev builds use a plain-text file).
  ZED_RELEASE_CHANNEL=nightly RUSTUP_TOOLCHAIN="$toolchain" \
    cargo build --release --manifest-path "$source_root/Cargo.toml" -p zed ${features[@]+"${features[@]}"}
  RUSTUP_TOOLCHAIN="$toolchain" cargo build --manifest-path "$project_root/gateway/Cargo.toml"
else
  RUSTUP_TOOLCHAIN=stable cargo build --manifest-path "$source_root/Cargo.toml" -p zed
  RUSTUP_TOOLCHAIN=stable cargo build --manifest-path "$project_root/gateway/Cargo.toml"
fi
printf 'Built patched Zed and ZedLink gateway. Open ZedLink: Configure in Zed.\n'
