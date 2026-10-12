#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="$project_root/zed-source"
patch="$project_root/patches/zed-native-agent-remote-control.patch"
pinned_revision="c66312b200d113694fca08c1d468669028a09a0e"
zed_fork="https://github.com/tjnull/zed.git"
zed_branch="zedlink/native-agent-remote-control"
zed_upstream="https://github.com/zed-industries/zed.git"

if [[ ! -d "$source_root/.git" ]]; then
  if [[ -e "$source_root" ]]; then
    printf 'Refusing to replace existing non-Git path: %s\n' "$source_root" >&2
    exit 1
  fi
  git clone --branch "$zed_branch" --single-branch "$zed_fork" "$source_root"
  git -C "$source_root" remote add upstream "$zed_upstream"
fi

actual_revision="$(git -C "$source_root" rev-parse HEAD)"
if [[ "$actual_revision" != "$pinned_revision" ]] &&
  ! git -C "$source_root" merge-base --is-ancestor "$pinned_revision" "$actual_revision"; then
  printf 'Expected Zed revision %s or a ZedLink fork branch based on it; found %s. No changes made.\n' \
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

RUSTUP_TOOLCHAIN=stable cargo build --manifest-path "$source_root/Cargo.toml" -p zed
RUSTUP_TOOLCHAIN=stable cargo build --manifest-path "$project_root/gateway/Cargo.toml"
printf 'Built patched Zed and ZedLink gateway. Open ZedLink: Configure in Zed.\n'
