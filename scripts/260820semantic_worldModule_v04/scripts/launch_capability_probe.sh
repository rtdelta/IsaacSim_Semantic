#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_ROOT="${ISAAC_ROOT:-/root/isaacsim}"
RUNTIME_ROOT="${SEMANTIC_WORLD_RUNTIME_ROOT:-${PROJECT_ROOT}/.runtime/capability_probe}"
OUTPUT_PATH="${1:-${PROJECT_ROOT}/.runtime/capability_report.json}"

mkdir -p "${RUNTIME_ROOT}/home" "${RUNTIME_ROOT}/tmp" \
  "${RUNTIME_ROOT}/cache/xdg" "${RUNTIME_ROOT}/cache/ov" \
  "${RUNTIME_ROOT}/cache/cuda" "${RUNTIME_ROOT}/cache/optix" \
  "$(dirname "${OUTPUT_PATH}")"

export HOME="${RUNTIME_ROOT}/home"
export TMPDIR="${RUNTIME_ROOT}/tmp"
export XDG_CACHE_HOME="${RUNTIME_ROOT}/cache/xdg"
export OMNI_USER_DIR="${RUNTIME_ROOT}/cache/ov"
export CUDA_CACHE_PATH="${RUNTIME_ROOT}/cache/cuda"
export OPTIX_CACHE_PATH="${RUNTIME_ROOT}/cache/optix"
export LD_LIBRARY_PATH="${ISAAC_ROOT}/kit/python/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

source "${ISAAC_ROOT}/setup_python_env.sh"
export LD_LIBRARY_PATH="${ISAAC_ROOT}/kit/python/lib:${LD_LIBRARY_PATH}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH}"

exec "${ISAAC_ROOT}/python.sh" \
  "${PROJECT_ROOT}/scripts/capability_probe.py" \
  --output "${OUTPUT_PATH}"
