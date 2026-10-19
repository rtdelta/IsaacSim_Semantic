"""Robot instrumentation adapter to the v04 run diagnostics."""
from functools import wraps


def timed(name):
    def decorate(function):
        @wraps(function)
        def measured(self, *args, **kwargs):
            monitor = getattr(self, 'performance', None)
            if monitor is None: monitor = getattr(getattr(self, 'runtime', None), 'performance', None)
            if monitor is None: return function(self, *args, **kwargs)
            with monitor.span(name): return function(self, *args, **kwargs)
        return measured
    return decorate

