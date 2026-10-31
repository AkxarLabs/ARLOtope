#!/bin/sh
# Build the release archive from the committed tree: product source only, without the dev-only
# folders (tests, branding concepts, CI) or any local Lab state. Usage: build-archive.sh [out.tar.gz]
set -eu
case "${1:-arlotope.tar.gz}" in /*) out="${1:-arlotope.tar.gz}" ;; *) out="$PWD/${1:-arlotope.tar.gz}" ;; esac
cd "$(dirname "$0")/.."
git archive --format=tar.gz --prefix=ARLOtope/ -o "$out" HEAD -- . \
  ':!tests' ':!branding' ':!.github' \
  ':!lab/config.yaml' ':!lab/REGISTRY.md' ':!lab/knowledge'
