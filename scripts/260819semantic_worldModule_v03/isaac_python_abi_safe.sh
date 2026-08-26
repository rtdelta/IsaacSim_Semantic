#!/usr/bin/env bash
set -euo pipefail

# Some hosted images put /usr/lib ahead of the Isaac Sim runtime in
# LD_LIBRARY_PATH. That makes Isaac's CPython executable load the host
# libpython while importing its bundled stdlib extension modules, which can
# segfault as early as omni.kit.async_engine startup. Reorder only this
# process environment; do not mutate the Isaac Sim installation.
isaac_root="${ISAACSIM_ROOT:-/root/isaacsim}"
python_lib="$isaac_root/kit/python/lib"
python_launcher="$isaac_root/python.sh"

if [[ ! -d "$python_lib" || ! -x "$python_launcher" ]]; then
  printf 'Invalid Isaac Sim runtime: %s\n' "$isaac_root" >&2
  exit 72
fi

ordered="$python_lib"
IFS=':' read -r -a entries <<< "${LD_LIBRARY_PATH:-}"
for entry in "${entries[@]}"; do
  if [[ -n "$entry" && "$entry" != "$python_lib" ]]; then
    ordered="$ordered:$entry"
  fi
done
export LD_LIBRARY_PATH="$ordered"

exec "$python_launcher" "$@"
