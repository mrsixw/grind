#!/usr/bin/env bash
set -euo pipefail

version="$1"
tag="v${version}"

gh release create "${tag}" ./dist/grind \
  man1/grind.1.gz \
  completions/grind.bash \
  completions/_grind \
  completions/grind.fish \
  --title "${tag}" \
  --generate-notes \
  --target "$(git rev-parse HEAD)"
