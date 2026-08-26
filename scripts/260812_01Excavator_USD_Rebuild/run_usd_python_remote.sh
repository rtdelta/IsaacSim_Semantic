#!/usr/bin/env bash
set -euo pipefail

# Minimal Isaac Sim 6.0.1 USD runtime. This intentionally avoids starting Kit;
# it is suitable for deterministic asset inspection and converter API probes.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USD_LIB_DIR="/root/isaacsim/extscache/omni.usd.libs-1.0.3+f9bf0dda.lx64.r.cp312"
GSPLAT_DIR="/root/isaacsim/extscache/omni.kit.converter.gsplat-0.1.14+110.1.0.lx64.r.cp312.u7f4"
NUMPY_DIR="/root/isaacsim/extscache/omni.kit.pip_archive-0.0.0+f9bf0dda.lx64.cp312/pip_prebundle"
PARTICLE_SCHEMA_DIR="/root/isaacsim/extscache/omni.usd.schema.usd_particle_field-1.0.0+f9bf0dda"

export PYTHONUNBUFFERED=1
export PYTHONPATH="${PROJECT_DIR}/tools:${USD_LIB_DIR}:${GSPLAT_DIR}/pip_prebundle:${NUMPY_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${USD_LIB_DIR}/bin:/root/isaacsim/kit:/root/isaacsim/kit/plugins${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PXR_PLUGINPATH_NAME="${USD_LIB_DIR}/bin/usd:${PARTICLE_SCHEMA_DIR}/usd_plugins${PXR_PLUGINPATH_NAME:+:${PXR_PLUGINPATH_NAME}}"

exec /root/isaacsim/kit/python/bin/python3 "$@"
