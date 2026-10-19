"""All products have explicit requested state, never inferred GPU idleness."""
from .diagnostics import NullDiagnostics
from .tickets import SampleError


class ProductGate:
    def __init__(self, diagnostics=None):
        self.diag=diagnostics or NullDiagnostics(); self.products={}; self.requested={}; self.closed=False
    def add(self, key, product):
        if key in self.products: raise ValueError('Duplicate product '+key)
        self.products[key]=product
        self.set([key],False,'product_created')
    def set(self, keys, enabled, reason):
        if self.closed: raise SampleError('resource_handle_invalid','Gate is closed')
        for key in keys:
            if self.requested.get(key) is enabled: continue
            self.diag.event('sensor_updates_requested',sensor_id=key,enabled=enabled,reason=reason)
            try: self.products[key].hydra_texture.set_updates_enabled(enabled)
            except Exception as exc:
                self.diag.warning('resource_handle_invalid',str(exc),sensor_id=key); raise
            self.requested[key]=enabled
            self.diag.event('sensor_updates_applied',sensor_id=key,enabled=enabled,reason=reason,
                            observation='API returned; not proof of GPU inactivity')
    def all(self, enabled, reason): self.set(list(self.products),enabled,reason)
    def kind(self, kind, enabled, reason): self.set([k for k in self.products if k.startswith(kind+'/')],enabled,reason)
