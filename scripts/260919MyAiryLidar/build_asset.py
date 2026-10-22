"""Build a self-contained instantaneous MyOS0-direction lidar using Python stdlib."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREFIX = 'omni:sensor:Core:'


def read_value(text, name):
    match = re.search(r'^\s*\w+(?:\[\])?\s+' + re.escape(PREFIX + name) + r'\s*=\s*(.+)$', text, re.M)
    if not match:
        raise ValueError('Missing source attribute: ' + name)
    return json.loads(match.group(1))


def array(name, kind, values):
    rows = [', '.join(format(v, '.9g') if isinstance(v, float) else str(v) for v in values[i:i+16])
            for i in range(0, len(values), 16)]
    return f'    {kind}[] {PREFIX}{name} = [\n        ' + ',\n        '.join(rows) + '\n    ]'


def build():
    source = ROOT / 'reference/MyOS0_config.usda'
    text = source.read_text(encoding='utf-8')
    elevations = read_value(text, 'emitterState:s001:elevationDeg')
    offsets = read_value(text, 'emitterState:s001:azimuthDeg')
    rate = read_value(text, 'scanRateBaseHz')
    firing = read_value(text, 'patternFiringRateHz')
    assert firing % rate == 0
    cols, rows = firing // rate, len(elevations)
    assert len(offsets) == rows == 96 and cols == 892
    assert min(elevations) == 0 and max(elevations) == 90
    # RTX spherical azimuth is clockwise; canonical scan phase is zero.
    sign = 1 if read_value(text, 'rotationDirection') == 'CW' else -1
    azimuth = [(offsets[row] + sign * col * 360.0 / cols + 180) % 360 - 180
               for row in range(rows) for col in range(cols)]
    elevation = [e for e in elevations for _ in range(cols)]
    total = rows * cols
    effective = json.loads((ROOT / 'reference/MyOS0_effective_attributes.json').read_text(encoding='utf-8'))
    source_peak = float(effective[PREFIX + 'peakPowerW']['value'])
    folder = ROOT / 'assets/MyAiry'
    (folder / 'config').mkdir(parents=True, exist_ok=True)
    lines = ['#usda 1.0', '(', '    defaultPrim = "OmniLidar"', '    metersPerUnit = 1',
             '    upAxis = "Z"', ')', '',
             '# Synthetic flash-style model: MyOS0 angular samples, NZ3 scheduling.',
             '# Rows preserve the source elevation order (90 degrees down to 0).',
             '# Pole duplicates are intentional; no additional 360-degree seam sample.',
             'def OmniLidar "OmniLidar" (',
             '    prepend apiSchemas = ["OmniSensorGenericLidarCoreAPI", "OmniSensorGenericLidarCoreEmitterStateAPI:s001"]',
             ')', '{']
    attrs = {
        'scanType': ('token', 'SOLID_STATE'), 'instantLidar': ('bool', True),
        'accumulateOutputs': ('bool', True), 'scanRateBaseHz': ('uint', rate),
        'patternFiringRateHz': ('uint', rate), 'reportRateBaseHz': ('uint', rate),
        'numberOfEmitters': ('uint', total), 'numberOfChannels': ('uint', total),
        'numLines': ('uint', rows), 'rangeCount': ('uint', 0),
        'elementsCoordsType': ('token', 'CARTESIAN'),
        'outputFrameOfReference': ('token', 'SENSOR'),
        'outputMotionCompensationState': ('token', 'NONCOMPENSATED'),
        'rangeOffsetM': ('float', 0),
        # Empirically validated on RTX 6.0.1-rc.7: expanding 96 rotary emitters
        # to 96*892 simultaneous emitters needs this synthetic power scaling.
        # This is NOT a physical hardware power specification.
        'peakPowerW': ('float', source_peak * cols),
        # Resolve this default explicitly rather than inheriting an Ouster asset.
        'minReflectionRangeM': ('float', 200),
    }
    for kind, names in [
        ('float', ('avgPowerW', 'nearRangeM', 'farRangeM', 'minReflectance', 'rangeAccuracyM',
                   'rangeResolutionM', 'azimuthErrorMean', 'azimuthErrorStd',
                   'elevationErrorMean', 'elevationErrorStd')),
        ('uint', ('maxReturns', 'pulseTimeNs')),
        ('token', ('rayType', 'intensityMappingType', 'intensityProcessing')),
        ('bool', ('skipDroppingInvalidPoints',)),
    ]:
        for name in names:
            attrs[name] = (kind, read_value(text, name))
    for name, (kind, value) in attrs.items():
        encoded = json.dumps(bool(value) if kind == 'bool' else value)
        lines.append(f'    {kind} {PREFIX}{name} = {encoded}')
    lines += [f'    float omni:sensor:tickRate = {rate}',
              '    string omni:sensor:modelName = "MyAiry_Instant_96x892_10Hz"',
              '    custom string[] _replicator:rendervar:GenericModelOutput:channels = ["BASIC"]',
              array('numRaysPerLine', 'uint', [cols] * rows),
              array('emitterState:s001:azimuthDeg', 'float', azimuth),
              array('emitterState:s001:elevationDeg', 'float', elevation),
              array('emitterState:s001:channelId', 'uint', list(range(1, total + 1))),
              array('emitterState:s001:bank', 'uint', [r for r in range(rows) for _ in range(cols)]),
              array('emitterState:s001:fireTimeNs', 'uint', [0] * total)]
    for name in ('horOffsetM', 'vertOffsetM', 'distanceCorrectionM'):
        lines.append(array('emitterState:s001:' + name, 'float', [0] * total))
    for name in ('focalDistM', 'focalSlope', 'reportRateDiv'):
        original = read_value(text, 'emitterState:s001:' + name)
        lines.append(array('emitterState:s001:' + name, 'float', [v for v in original for _ in range(cols)]))
    lines += ['    double3 xformOp:translate = (0, 0, 0)',
              '    quatd xformOp:orient = (1, 0, 0, 0)',
              '    double3 xformOp:scale = (1, 1, 1)',
              '    uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient", "xformOp:scale"]', '}']
    (folder / 'config/MyAiry_scan.usda').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (folder / 'MyAiry.usda').write_text('''#usda 1.0
(
    defaultPrim = "MyAiry"
    metersPerUnit = 1
    upAxis = "Z"
    timeCodesPerSecond = 60
)
def Xform "MyAiry" (
    kind = "component"
    assetInfo = {
        string name = "MyAiry"
        string version = "1.0"
    }
)
{
    custom string airy:model = "Synthetic instantaneous lidar; MyOS0 directions, NZ3 scheduling"
    custom string airy:coverage = "360-degree azimuth, elevation 0..90 degrees, local +Z hemisphere"
    custom string airy:sampleOrder = "row-major; row=emitterId//892, column=emitterId%892; row 0 is pole"
    custom uint airy:rows = 96
    custom uint airy:columns = 892
    custom string airy:powerNormalization = "Synthetic flash peakPowerW = source peakPowerW * 892; not hardware power"
    def OmniLidar "sensor" (
        prepend references = @./config/MyAiry_scan.usda@
    ) {}
    def Xform "geometry" (active = false)
    {
        custom string airy:purpose = "Reserved for optional housing; no geometry exclusion is applied"
    }
}
''', encoding='utf-8')
    manifest = dict(model='MyAiry', source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    rows=rows, columns=cols, samples=total, unique_geometric_directions=(rows-1)*cols+1,
                    duplicate_pole_samples=cols-1, azimuth_step_degrees=360/cols,
                    elevation_source=elevations, source_rotation=read_value(text, 'rotationDirection'),
                    phase_degrees=0, authored_settings={k:v for k, (_,v) in attrs.items()})
    manifest['power_normalization'] = dict(source_peak_power_w=source_peak, factor=cols,
        synthetic_peak_power_w=source_peak*cols,
        rationale='Validated against rotary/flash controls; not a real-device power specification')
    manifest['files'] = {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in folder.rglob('*.usda')}
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('model','samples','unique_geometric_directions','files')}, indent=2))


if __name__ == '__main__':
    build()
