"""Rebuild the bag-calibrated NZ3 asset, calibration evidence and plots locally."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from nz3_model import (ROWS, COLS, SOURCE_NAMES, load_bag, fit_pattern, ideal_grid,
                       validate_pattern, angle_error, error_stats)

ROOT = Path(__file__).resolve().parent


def dump_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def array_attr(kind, name, values):
    values = np.asarray(values).ravel()
    format_value = (lambda v: str(int(v))) if kind == 'uint' else (lambda v: f'{float(v):.7f}')
    chunks = [', '.join(format_value(v) for v in values[i:i+16]) for i in range(0, len(values), 16)]
    return f'    {kind}[] omni:sensor:Core:{name} = [\n        '+',\n        '.join(chunks)+'\n    ]\n'


def write_assets(table, asset_dir):
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir/'config').mkdir(exist_ok=True)
    core = '''#usda 1.0
(
    defaultPrim = "OmniLidar"
    metersPerUnit = 1
    upAxis = "Z"
)
# One complete fixed-FOV pattern. Geometry-only, instantaneous acquisition.
# Row-major samples: ring = emitterId // 480, column = emitterId % 480.
def OmniLidar "OmniLidar" (
    prepend apiSchemas = ["OmniSensorGenericLidarCoreAPI", "OmniSensorGenericLidarCoreEmitterStateAPI:s001"]
)
{
    token omni:sensor:Core:scanType = "SOLID_STATE"
    uint omni:sensor:Core:scanRateBaseHz = 10
    uint omni:sensor:Core:patternFiringRateHz = 10
    float omni:sensor:tickRate = 10
    bool omni:sensor:Core:accumulateOutputs = 1
    bool omni:sensor:Core:instantLidar = 1
    uint omni:sensor:Core:numberOfEmitters = 46080
    uint omni:sensor:Core:numberOfChannels = 46080
    uint omni:sensor:Core:numLines = 96
    uint omni:sensor:Core:maxReturns = 1
    token omni:sensor:Core:rayType = "IDEALIZED"
    token omni:sensor:Core:elementsCoordsType = "CARTESIAN"
    token omni:sensor:Core:outputFrameOfReference = "SENSOR"
    token omni:sensor:Core:outputMotionCompensationState = "NONCOMPENSATED"
    float omni:sensor:Core:nearRangeM = 0.2
    float omni:sensor:Core:farRangeM = 115
    uint omni:sensor:Core:rangeCount = 0
    float omni:sensor:Core:rangeAccuracyM = 0
    float omni:sensor:Core:rangeResolutionM = 0.00001
    float omni:sensor:Core:azimuthErrorMean = 0
    float omni:sensor:Core:azimuthErrorStd = 0
    float omni:sensor:Core:elevationErrorMean = 0
    float omni:sensor:Core:elevationErrorStd = 0
    float[] omni:sensor:Core:originErrorMean = [0, 0, 0]
    float[] omni:sensor:Core:originErrorStd = [0, 0, 0]
    float omni:sensor:Core:minReflectance = 0.000001
    float omni:sensor:Core:minReflectionRangeM = 70
    float omni:sensor:Core:waveLengthNm = 905
    bool omni:sensor:Core:skipDroppingInvalidPoints = 0
    custom string[] _replicator:rendervar:GenericModelOutput:channels = ["BASIC"]
    custom string nz3:scope = "FOV and bag-calibrated sampling directions only; no optical/noise/timing fidelity claim"
    custom string nz3:coordinates = "+X forward, +Y left, +Z up; asset XYZ = bag(y,-x,z)"
    custom float nz3:nominalHorizontalFovDeg = 240
    custom float nz3:nominalVerticalFovDeg = 80
'''
    for kind, name, values in [
        ('uint', 'numRaysPerLine', np.full(ROWS, COLS)),
        # RTX lidar azimuth is clockwise; the calibration uses +Y-left CCW angles.
        ('float', 'emitterState:s001:azimuthDeg', -table['azimuth_deg']),
        ('float', 'emitterState:s001:elevationDeg', table['elevation_deg']),
        # Isaac Sim 6.0 sensor checker requires channels 1..N (emitters remain 0..N-1).
        ('uint', 'emitterState:s001:channelId', np.arange(1, ROWS*COLS+1)),
        ('uint', 'emitterState:s001:bank', table['ring']),
        ('uint', 'emitterState:s001:fireTimeNs', np.zeros(ROWS*COLS, dtype=int)),
    ]:
        core += array_attr(kind, name, values)
    (asset_dir/'config/NZ3_scan.usda').write_text(core+'}\n', encoding='utf-8')
    write_entry(asset_dir)


def write_entry(asset_dir):
    """Compose the scan and optional Blender housing without regenerating angles."""
    entry = '''#usda 1.0
(
    defaultPrim = "NZ3"
    metersPerUnit = 1
    upAxis = "Z"
    timeCodesPerSecond = 60
)
def Xform "NZ3" (
    kind = "component"
    assetInfo = {
        string name = "NZ3"
        string version = "1.1"
    }
)
{
    custom string nz3:model = "NZ3 bag-calibrated 480x96 sampling model"
    custom string nz3:forwardAxis = "+X"
    custom string nz3:coordinateConvention = "+X forward, +Y left, +Z up; root is the ray origin"
    custom uint nz3:rows = 96
    custom uint nz3:columns = 480
    custom string nz3:sampleOrder = "row-major; ring=emitterId//480; column=emitterId%480; authored channelId=emitterId+1; GMO channelId=emitterId"
    def OmniLidar "sensor" (
        prepend references = @./config/NZ3_scan.usda@
    )
    {
    }
    def Xform "geometry"
    {
        custom string nz3:purpose = "Reserved for a future NZ3 housing mesh; currently empty"
    }
}
'''
    if (asset_dir/'geometry/NZ3_housing.usda').exists():
        metadata=json.loads((ROOT/'source/housing/housing_manifest.json').read_text(encoding='utf-8'))
        offset=metadata['range_offset_m']
        assert metadata['max_vertex_radius_m'] < offset < .2
        entry=entry.replace('string version = "1.1"','string version = "1.2"')
        entry=entry.replace('    {\n    }\n    def Xform "geometry"',
            '    {\n        float omni:sensor:Core:rangeOffsetM = '+str(offset)+'\n'
            '        custom string nz3:selfOcclusionHandling = "Ignore all geometry within rangeOffsetM, not a mesh-specific mask"\n'
            '    }\n    def Xform "geometry"')
        entry=entry.replace('    def Xform "geometry"\n    {\n        custom string nz3:purpose = "Reserved for a future NZ3 housing mesh; currently empty"\n    }',
            '    def Xform "geometry" (\n        prepend references = @./geometry/NZ3_housing.usda@\n    )\n'
            '    {\n        custom string nz3:purpose = "Simple visual NZ3 housing made in Blender"\n'
            '        custom float3 nz3:dimensionsXYZM = (0.086, 0.071, 0.100)\n'
            '        custom bool nz3:opticalOriginApproximate = true\n'
            '        custom string nz3:opticalOriginNote = "Housing centred on ray origin; mechanical optical-centre offset not calibrated"\n    }')
    (asset_dir/'MyNZ3.usda').write_text(entry,encoding='utf-8')
    # Keep old local scene references valid; both names resolve to the same model.
    (asset_dir/'NZ3.usda').write_text('''#usda 1.0
(
    defaultPrim = "NZ3"
    metersPerUnit = 1
    upAxis = "Z"
)
# Compatibility entry. New scenes should reference MyNZ3.usda.
def Xform "NZ3" (
    prepend references = @./MyNZ3.usda@
)
{
}
''', encoding='utf-8')


def plot_reports(table, observed_az, observed_el, report_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    im=axes[0,0].scatter(table['azimuth_deg'], table['elevation_deg'], c=table['ring'], s=.35, cmap='turbo', rasterized=True)
    axes[0,0].set(title='Complete NZ3 sampling pattern (46,080 rays)', xlabel='Azimuth (deg)', ylabel='Elevation (deg)', xlim=(-122,122), ylim=(-41,41))
    fig.colorbar(im, ax=axes[0,0], label='ring')
    colors=['#156b9e','#3baf9c','#efbb4a','#dd724d','#a19fc0']
    cmap=ListedColormap(colors)
    im=axes[0,1].imshow(table['source'],origin='lower',aspect='auto',cmap=cmap,norm=BoundaryNorm(np.arange(-.5,5.5),5),extent=(-120,120,-.5,95.5))
    axes[0,1].set(title='Where every direction came from',xlabel='Nominal azimuth bin (deg)',ylabel='ring')
    fig.colorbar(im,ax=axes[0,1],ticks=range(5)).ax.set_yticklabels([SOURCE_NAMES[i].replace('_',' ') for i in range(5)])
    im=axes[1,0].imshow(table['observation_frames'],origin='lower',aspect='auto',extent=(-120,120,-.5,95.5),cmap='viridis')
    axes[1,0].set(title='Observed frame support (not a permanent hit mask)',xlabel='Nominal azimuth bin (deg)',ylabel='ring')
    fig.colorbar(im,ax=axes[1,0],label='frames')
    for col,label in [(120,'Negative half-FOV'),(360,'Positive half-FOV')]:
        axes[1,1].plot(np.arange(ROWS),table['elevation_deg'][:,col],label=label)
    axes[1,1].plot(np.arange(ROWS),ideal_grid()[1][:,0],ls='--',color='gray',label='Handbook scaffold')
    axes[1,1].set(title='Nonuniform vertical sampling is retained',xlabel='ring',ylabel='Elevation (deg)');axes[1,1].legend()
    fig.savefig(report_dir/'calibration_overview.png',dpi=160);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bag',type=Path,default=ROOT/'inputs/2026-09-09-14-33-50.bag')
    parser.add_argument('--asset-only',action='store_true',help='Package the existing calibration without refitting the bag')
    args=parser.parse_args()
    cal=ROOT/'calibration';report=ROOT/'reports'
    cal.mkdir(exist_ok=True);report.mkdir(exist_ok=True)
    if args.asset_only:
        with np.load(cal/'rays.npz',allow_pickle=False) as data:
            table=dict(data)
        validate_pattern(table)
        write_assets(table,ROOT/'assets/NZ3')
        print('ASSET_READY',ROOT/'assets/NZ3/MyNZ3.usda',flush=True)
        return
    az,el,counts,frames=load_bag(args.bag)
    print(f'Read {len(frames)} frames; fitting a 96x480 pattern.',flush=True)
    np.savez_compressed(cal/'frame_observations.npz',azimuth_deg=az,elevation_deg=el,points_per_cell=counts)
    dump_json(cal/'frames.json',frames)
    table=fit_pattern(az,el)
    validation=validate_pattern(table)
    np.savez_compressed(cal/'rays.npz',**table)
    # Out-of-sample check: every fifth frame is excluded from this validation fit.
    holdout=np.arange(len(frames))%5==4
    training_table=fit_pattern(az[~holdout],el[~holdout])
    mask=np.isfinite(az[holdout])
    error=angle_error(az[holdout],el[holdout],training_table['azimuth_deg'],training_table['elevation_deg'])
    observed_only=mask & (training_table['source'][None,:,:]==0)
    handbook_error=angle_error(az[holdout],el[holdout],*ideal_grid())
    validation['holdout']=dict(training_frames=int((~holdout).sum()),held_out_frames=int(holdout.sum()),
                              all_observed_cells=error_stats(error[mask]),
                              measured_training_cells=error_stats(error[observed_only]),
                              handbook_on_same_measured_cells=error_stats(handbook_error[observed_only]))
    if validation['holdout']['measured_training_cells']['p95_deg'] > .30:
        raise AssertionError('Held-out measured-ray p95 error exceeds 0.30 degrees')
    write_assets(table,ROOT/'assets/NZ3')
    plot_reports(table,az,el,report)
    manifest=dict(model='NZ3',version=1,scope='Horizontal/vertical FOV and one bag-calibrated angular sampling pattern',
                  bag_file=args.bag.name,bag_sha256=hashlib.sha256(args.bag.read_bytes()).hexdigest(),
                  rows=ROWS,columns=COLS,source_codes=SOURCE_NAMES,
                  nominal_horizontal_fov_deg=240,nominal_vertical_fov_deg=80,
                  bag_to_asset_rotation=[[0,1,0],[-1,0,0],[0,0,1]],
                  rtx_mapping=dict(azimuth='RTX clockwise angle = negative of calibration azimuth',
                                   emitter_id='0..46079',channel_id='authored configuration: 1..46080',
                                   gmo_channel_id='observed Isaac Sim 6.0.1-rc.7 output: 0..46079',
                                   ring='emitterId // 480; column = emitterId % 480'),
                  sampling='Cell-centred 0.5 degree horizontal bin assignment. Ring ids assumed to correspond to rows 0..95.',
                  fitting='Median of per-frame cell medians; minimum 3 frames; MAD az<=0.15deg, el<=0.20deg.',
                  filling='Per-half-FOV horizontal interpolation; nearest correction at unobserved sector edges; interpolate missing rings to handbook edge-centre anchors.',
                  geometry_acquisition='Instantaneous full-frame pattern, all fireTimeNs=0. Actual temporal scan pattern is outside this version.',
                  rejected_outside_nominal_fov=sum(f['outside_nominal_fov'] for f in frames),
                  validation=validation)
    dump_json(cal/'manifest.json',manifest)
    dump_json(report/'local_validation.json',validation)
    print(json.dumps(validation,indent=2),flush=True)
    print('ASSET_READY',ROOT/'assets/NZ3/MyNZ3.usda',flush=True)


if __name__=='__main__':
    main()
