#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_ROOT="${ISAAC_ROOT:-/root/isaacsim}"
RUNNER_ROOT="${SEMANTIC_WORLD_RUNTIME_ROOT:-${PROJECT_ROOT}/.runtime/job_runner}"

mkdir -p "${RUNNER_ROOT}/home" "${RUNNER_ROOT}/tmp"

export HOME="${RUNNER_ROOT}/home"
export TMPDIR="${RUNNER_ROOT}/tmp"
export LD_LIBRARY_PATH="${ISAAC_ROOT}/kit/python/lib:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

source "${ISAAC_ROOT}/setup_python_env.sh"
export LD_LIBRARY_PATH="${ISAAC_ROOT}/kit/python/lib:${LD_LIBRARY_PATH}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH}"

exec "${ISAAC_ROOT}/python.sh" -m semantic_world_v04.supervisor.job_runner_cli "$@"
