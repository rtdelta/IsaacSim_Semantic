"""Physical identities and observed CUDA output paths; no visibility remapping."""
import csv
import ctypes
import io
import json
import os
import subprocess

def canonical_pci(value):
    domain, bus, slot = str(value).lower().split(':')
    return f'{int(domain,16):04x}:{bus}:{slot}'

def inventory():
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,pci.bus_id,name,memory.total',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=10)
    return [dict(index=int(row[0]), uuid=row[1].strip(), pci=canonical_pci(row[2].strip()),
                 name=row[3].strip(), memory_mib=int(row[4])) for row in csv.reader(io.StringIO(result.stdout))]

def resolve_device(value, devices=None):
    devices = inventory() if devices is None else devices
    key = str(value).strip()
    matches = [d for d in devices if key in (str(d['index']), d['uuid'], d['pci'])]
    if len(matches) != 1:
        raise ValueError('Select one available GPU by UUID, PCI bus address or index')
    return dict(matches[0])

def cuda_inventory():
    lib = ctypes.CDLL('libcuda.so.1')
    def call(name, *args):
        result = getattr(lib, name)(*args)
        if result:
            raise RuntimeError(f'{name} failed with CUDA status {result}')
    call('cuInit', 0)
    count = ctypes.c_int()
    call('cuDeviceGetCount', ctypes.byref(count))
    devices = []
    for ordinal in range(count.value):
        handle = ctypes.c_int()
        call('cuDeviceGet', ctypes.byref(handle), ordinal)
        bus = ctypes.create_string_buffer(64)
        call('cuDeviceGetPCIBusId', bus, len(bus), handle)
        devices.append({'ordinal': ordinal, 'pci': canonical_pci(bus.value.decode())})
    return devices

def resolve_cuda_ordinal(requested,cuda=None):
    cuda=cuda_inventory() if cuda is None else cuda
    matches=[d for d in cuda if d['pci']==requested['pci']]
    if len(matches)!=1:raise RuntimeError('Requested physical GPU is absent from the CUDA device roster')
    return matches[0]['ordinal']

def kit_binding():
    """Resolve CUDA ordinal from physical bus, independently of renderer's index."""
    requested = json.loads(os.environ.get('SV07_DEVICE', 'null'))
    if requested is None:
        requested = resolve_device(0)
    cuda = cuda_inventory()
    ordinal=resolve_cuda_ordinal(requested,cuda)
    import carb.settings
    settings = carb.settings.get_settings()
    return {'requested': requested, 'cuda_roster': cuda, 'cuda_ordinal': ordinal,
            'annotator_device': 'cuda:' + str(ordinal),
            'renderer_index_setting': settings.get('/renderer/activeGpu'),
            'physics_index_setting': settings.get('/physics/cudaDevice'),
            'renderer_identity_evidence': 'requested index; per-node source device and callback arrays validate the data path'}

def observe_array(value, binding):
    device = getattr(value, 'device', None)
    if device is None:
        return {'device': 'cpu/numpy', 'pci': None, 'physical_identity': 'not a GPU array'}
    text = str(device)
    if text == 'cpu':
        return {'device': text, 'pci': None, 'physical_identity': 'CPU'}
    ordinal = getattr(device, 'ordinal', None)
    if ordinal is None and text.startswith('cuda:'):
        ordinal = int(text.split(':')[1])
    pci = next((d['pci'] for d in binding['cuda_roster'] if d['ordinal'] == ordinal), None)
    if pci != binding['requested']['pci']:
        raise RuntimeError('Sensor array is on a different or unidentified GPU: ' + text)
    return {'device': text, 'cuda_ordinal': ordinal, 'pci': pci, 'uuid': binding['requested']['uuid'],
            'physical_identity': 'CUDA Driver ordinal-to-PCI match'}
