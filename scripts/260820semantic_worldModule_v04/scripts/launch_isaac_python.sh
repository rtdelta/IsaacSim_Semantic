#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_ROOT="${ISAAC_ROOT:-/root/isaacsim}"
RUNTIME_ROOT="${SEMANTIC_WORLD_RUNTIME_ROOT:-${PROJECT_ROOT}/.runtime/isaac_python}"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <python-script> [args...]" >&2
  exit 2
fi

SCRIPT_PATH="$1"
shift
if [[ "${SCRIPT_PATH}" != /* ]]; then
  SCRIPT_PATH="${PROJECT_ROOT}/${SCRIPT_PATH}"
fi

mkdir -p "${RUNTIME_ROOT}/home" "${RUNTIME_ROOT}/tmp" \
  "${RUNTIME_ROOT}/cache/xdg" "${RUNTIME_ROOT}/cache/ov" \
  "${RUNTIME_ROOT}/cache/cuda" "${RUNTIME_ROOT}/cache/optix"

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

exec "${ISAAC_ROOT}/python.sh" "${SCRIPT_PATH}" "$@"
