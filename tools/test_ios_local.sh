#!/usr/bin/env bash
# Local Apple-toolchain checks; never dispatches hosted CI.
set -euo pipefail
mode="${1:-build}"
destination="${2:-}"
case "$mode" in build|unit|ui|session) ;; *) echo 'Usage: bash tools/test_ios_local.sh build|unit|ui|session [simulator destination]' >&2; exit 2 ;; esac
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'NOT RUN: iOS compilation and UI tests require a Mac with Xcode.' >&2
  exit 2
fi
for executable in xcodebuild xcodegen; do
  command -v "$executable" >/dev/null || { echo "Missing prerequisite: $executable" >&2; exit 2; }
done
if [[ "$mode" != build && -z "$destination" ]]; then
  echo 'Supply an explicit disposable simulator destination, for example platform=iOS Simulator,id=<simulator UUID>.' >&2
  exit 2
fi
if [[ "$mode" != build && "$destination" != "platform=iOS Simulator,"* ]]; then
  echo 'This runner uses unsigned simulator builds. Use Xcode signing and Run for a physical iPhone.' >&2
  exit 2
fi
if [[ "$mode" == session ]]; then
  : "${ZEDLINK_E2E_THREAD_ID:?Set the exposed disposable thread ID after pairing the simulator}"
  : "${ZEDLINK_E2E_SEARCH_TEXT:?Set a known string in the disposable project}"
  # Apple documents TEST_RUNNER_ forwarding for xcodebuild's test runner.
  export TEST_RUNNER_ZEDLINK_E2E_THREAD_ID="$ZEDLINK_E2E_THREAD_ID"
  export TEST_RUNNER_ZEDLINK_E2E_SEARCH_TEXT="$ZEDLINK_E2E_SEARCH_TEXT"
  export TEST_RUNNER_ZEDLINK_E2E_TRANSCRIPT_TEXT="${ZEDLINK_E2E_TRANSCRIPT_TEXT:-}"
  export TEST_RUNNER_ZEDLINK_E2E_ALLOW_SEND="${ZEDLINK_E2E_ALLOW_SEND:-0}"
fi
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root/ios"
xcodegen generate
cd "$project_root"
derived_data="${ZEDLINK_IOS_DERIVED_DATA:-$(mktemp -d "${TMPDIR:-/tmp}/zedlink-ios-check.XXXXXX")}"
arguments=(-project ios/ZedLink.xcodeproj -scheme ZedLink -configuration Debug
  -derivedDataPath "$derived_data" CODE_SIGNING_ALLOWED=NO)
case "$mode" in
  build)
    xcodebuild "${arguments[@]}" -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' build-for-testing
    ;;
  unit)
    xcodebuild "${arguments[@]}" -destination "$destination" -parallel-testing-enabled NO -only-testing:ZedLinkTests test
    ;;
  ui)
    xcodebuild "${arguments[@]}" -destination "$destination" -parallel-testing-enabled NO \
      -only-testing:ZedLinkUITests/OnboardingUITests \
      -only-testing:ZedLinkUITests/SessionsPreviewUITests test
    ;;
  session)
    xcodebuild "${arguments[@]}" -destination "$destination" -parallel-testing-enabled NO -only-testing:ZedLinkUITests/SessionWorkspaceUITests test
    ;;
esac
printf 'Inspect build products and test results under %s\n' "$derived_data"
