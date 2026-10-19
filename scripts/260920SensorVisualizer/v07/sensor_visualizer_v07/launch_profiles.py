"""Separate interactive latency settings from formal frozen rendering."""
import os

def renderer_flags(role, options):
    enabled = role == 'interactive' and options['interactive_async']
    value = 'true' if enabled else 'false'
    return ['--/app/asyncRendering='+value,
            '--/app/asyncRenderingLowLatency='+value,
            # Keep throttling from reinterpreting prescribed-motion pause as capture.
            '--/exts/isaacsim.core.throttling/enable_async=false']

def record_actual(diag):
    import carb.settings
    settings = carb.settings.get_settings()
    names = ('/app/asyncRendering', '/app/asyncRenderingLowLatency',
             '/plugins/carb.tasking.plugin/threadCount', '/plugins/omni.tbb.globalcontrol/maxThreadCount',
             '/persistent/physics/numThreads', '/renderer/activeGpu', '/physics/cudaDevice')
    values = {name:settings.get(name) for name in names}
    diag.set_manifest(launch_role=os.environ.get('SV07_ROLE'), applied_settings=values)
    diag.event('launch_settings_observed', critical=True, settings=values,
               limitation='Settings values alone do not prove actual thread counts or GPU execution')
    return values
