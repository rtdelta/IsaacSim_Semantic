"""Resolve renderer device explicitly; no CUDA visibility remapping."""
import csv
import io
import subprocess

def resolve_gpu(value):
    from .device_binding import resolve_device
    return resolve_device(value)
