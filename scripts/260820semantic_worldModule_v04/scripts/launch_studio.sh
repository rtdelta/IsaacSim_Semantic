#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_ROOT="${ISAAC_ROOT:-/root/isaacsim}"
RUNTIME_ROOT="${SEMANTIC_WORLD_RUNTIME_ROOT:-${PROJECT_ROOT}/.runtime}"

mkdir -p "${RUNTIME_ROOT}/home" "${RUNTIME_ROOT}/tmp" "${RUNTIME_ROOT}/cache/xdg" "${RUNTIME_ROOT}/cache/ov" "${RUNTIME_ROOT}/cache/cuda" "${RUNTIME_ROOT}/cache/optix" "${RUNTIME_ROOT}/logs"

export HOME="${RUNTIME_ROOT}/home"
export TMPDIR="${RUNTIME_ROOT}/tmp"
export XDG_CACHE_HOME="${RUNTIME_ROOT}/cache/xdg"
export OMNI_USER_DIR="${RUNTIME_ROOT}/cache/ov"
export CUDA_CACHE_PATH="${RUNTIME_ROOT}/cache/cuda"
export OPTIX_CACHE_PATH="${RUNTIME_ROOT}/cache/optix"
export LD_LIBRARY_PATH="${ISAAC_ROOT}/kit/python/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="${PYTHONPATH:-}"

source "${ISAAC_ROOT}/setup_python_env.sh"
export LD_LIBRARY_PATH="${ISAAC_ROOT}/kit/python/lib:${LD_LIBRARY_PATH}"

exec "${ISAAC_ROOT}/kit/kit" "${PROJECT_ROOT}/apps/semantic_capture_studio.kit" --allow-root --ext-folder "${PROJECT_ROOT}/extensions" --ext-folder "${ISAAC_ROOT}/exts" --ext-folder "${ISAAC_ROOT}/extscache" --ext-folder "${ISAAC_ROOT}/extsUser" --enable semantic.capture.studio --/app/settings/persistent=0 "$@"
