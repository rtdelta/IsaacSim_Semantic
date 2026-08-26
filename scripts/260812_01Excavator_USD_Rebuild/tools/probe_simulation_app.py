#!/usr/bin/env python3
"""Start and close SimulationApp without loading a Stage.

This deliberately uses the conservative headless settings selected by the
project runtime profile.  It must not import or open any generated asset, so a
failure here is evidence about the Isaac Sim process rather than the USD.
"""

import sys

sys.argv = [sys.argv[0]]

from isaacsim import SimulationApp

app = SimulationApp(
    {
        "headless": True,
        "multi_gpu": False,
        "disable_viewport_updates": True,
    }
)
print("SIMULATION_APP_STARTED", flush=True)
for _ in range(3):
    app.update()
app.close()
print("SIMULATION_APP_CLOSED", flush=True)
