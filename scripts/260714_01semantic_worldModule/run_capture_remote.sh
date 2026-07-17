#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${PROJECT_DIR}/.runtime"

mkdir -p \
  "${RUNTIME_DIR}/tmp" \
  "${RUNTIME_DIR}/cache" \
  "${RUNTIME_DIR}/config" \
  "${RUNTIME_DIR}/home" \
  "${RUNTIME_DIR}/cuda_cache" \
  "${RUNTIME_DIR}/optix_cache"

export HOME="${RUNTIME_DIR}/home"
export TMPDIR="${RUNTIME_DIR}/tmp"
export XDG_CACHE_HOME="${RUNTIME_DIR}/cache"
export XDG_CONFIG_HOME="${RUNTIME_DIR}/config"
export CUDA_CACHE_PATH="${RUNTIME_DIR}/cuda_cache"
export OPTIX_CACHE_PATH="${RUNTIME_DIR}/optix_cache"
export PYTHONUNBUFFERED=1

cd "${RUNTIME_DIR}/home"
exec /root/isaacsim/python.sh "${PROJECT_DIR}/simulation_orchestrator.py" "$@"
