#!/usr/bin/env sh
set -eu
repo="${1:-.}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
patch="$script_dir/DIFF_FILE.patch"
git -C "$repo" apply --reverse --check "$patch"
git -C "$repo" apply --reverse "$patch"
