"""Background /proc and existing nvidia-smi sampling; no package installation."""
import os
import shutil
import threading


class ResourceSampler:
    def __init__(self, diagnostics):
        self.diag=diagnostics; self.pids={'isaac':os.getpid()}
        self.stop=threading.Event(); self.smi=shutil.which('nvidia-smi')
        from .resource_details import ResourceDetails
        self.details=ResourceDetails(diagnostics)
        self.thread=threading.Thread(target=self.run, name='sv07-resources', daemon=True); self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:self.diag.event('resource_sample',**self.details.sample(self.pids,self.smi))
            except Exception as exc:self.diag.event('resource_sample_failed',critical=True,error=str(exc))
            self.stop.wait(self.diag.config['resource_period_ms']/1000)

    def close(self): self.stop.set(); self.thread.join(timeout=5)
