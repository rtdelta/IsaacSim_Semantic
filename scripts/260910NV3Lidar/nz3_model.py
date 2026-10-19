"""Estimate one complete NZ3 angular pattern; no scene ranges are learned."""
from pathlib import Path
import warnings
import numpy as np

ROWS, COLS = 96, 480
H_FOV, V_FOV = 240.0, 80.0
SOURCE_NAMES = {0: 'measured', 1: 'horizontal_interpolation', 2: 'sector_edge_extension',
                3: 'missing_ring_interpolation', 4: 'handbook'}


def ideal_grid():
    az = -H_FOV / 2 + (np.arange(COLS) + .5) * H_FOV / COLS
    el = -V_FOV / 2 + (np.arange(ROWS) + .5) * V_FOV / ROWS
    return np.broadcast_to(az, (ROWS, COLS)).copy(), np.broadcast_to(el[:, None], (ROWS, COLS)).copy()


def directions(azimuth, elevation):
    """Unit vectors in the asset frame: +X forward, +Y left, +Z up."""
    az, el = np.radians(azimuth), np.radians(elevation)
    return np.stack((np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)), axis=-1)


def xyz_to_angles(xyz):
    """Observed bag frame -> asset frame: (X,Y,Z)asset = (y,-x,z)bag."""
    xyz = np.asarray(xyz, dtype=np.float64)
    az = (np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0])) - 90.0 + 180.0) % 360.0 - 180.0
    el = np.degrees(np.arctan2(xyz[:, 2], np.hypot(xyz[:, 0], xyz[:, 1])))
    return az, el


def frame_grid(points):
    """One robust observation per (ring, angular bin), with explicit rejection counts.

    Column ids are inferred angular bins, not manufacturer firing ids. Keeping
    each frame's contribution at one observation avoids weighting duplicate hits.
    """
    xyz = np.column_stack([points[n] for n in ('x', 'y', 'z')]).astype(np.float64)
    ring = points['ring'].astype(np.int64)
    nonzero = np.isfinite(xyz).all(axis=1) & (np.linalg.norm(xyz, axis=1) > 0)
    az, el = xyz_to_angles(xyz)
    in_fov = (az >= -120) & (az < 120) & (el >= -40) & (el <= 40)
    eligible = nonzero & in_fov & (ring >= 0) & (ring < ROWS)
    cols = np.floor((az[eligible] + 120) / .5).astype(np.int64)
    ids = ring[eligible] * COLS + cols
    obs_az = np.full(ROWS*COLS, np.nan, dtype=np.float32)
    obs_el = obs_az.copy()
    counts = np.zeros(ROWS*COLS, dtype=np.uint16)
    if len(ids):
        order = np.argsort(ids, kind='stable')
        ids, a, e = ids[order], az[eligible][order], el[eligible][order]
        unique, starts, count = np.unique(ids, return_index=True, return_counts=True)
        obs_az[unique], obs_el[unique], counts[unique] = a[starts], e[starts], count
        for cell, start, n in zip(unique[count > 1], starts[count > 1], count[count > 1]):
            obs_az[cell], obs_el[cell] = np.median(a[start:start+n]), np.median(e[start:start+n])
    stats = dict(input_points=len(points), zero_or_nonfinite=int((~nonzero).sum()),
                 outside_nominal_fov=int((nonzero & ~in_fov).sum()), eligible_points=int(eligible.sum()),
                 unique_cells=int((counts > 0).sum()), cells_with_multiple_points=int((counts > 1).sum()))
    return obs_az.reshape(ROWS, COLS), obs_el.reshape(ROWS, COLS), counts.reshape(ROWS, COLS), stats


def load_bag(path):
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore
    typestore = get_typestore(Stores.ROS1_NOETIC)
    typecodes = {1:'i1', 2:'u1', 3:'i2', 4:'u2', 5:'i4', 6:'u4', 7:'f4', 8:'f8'}
    azs, els, counts, metadata = [], [], [], []
    with Reader(Path(path)) as reader:
        conns = [c for c in reader.connections if c.msgtype == 'sensor_msgs/msg/PointCloud2']
        if len(conns) != 1:
            raise ValueError('Expected exactly one PointCloud2 connection for this NZ3 recording')
        for c, bag_time, raw in reader.messages(connections=conns):
            m = typestore.deserialize_ros1(raw, c.msgtype)
            if not {'x', 'y', 'z', 'ring'} <= {f.name for f in m.fields}:
                raise ValueError('Point cloud must have x,y,z,ring fields')
            if any(f.count != 1 for f in m.fields):
                raise ValueError('Only scalar PointCloud2 fields are supported')
            endian = '>' if m.is_bigendian else '<'
            dtype = np.dtype(dict(names=[f.name for f in m.fields],
                                  formats=[endian+typecodes[f.datatype] for f in m.fields],
                                  offsets=[f.offset for f in m.fields], itemsize=m.point_step))
            points = np.ndarray((m.height, m.width), dtype=dtype, buffer=m.data,
                                strides=(m.row_step, m.point_step)).reshape(-1)
            az, el, count, stats = frame_grid(points)
            azs.append(az); els.append(el); counts.append(count)
            metadata.append(dict(index=len(metadata), topic=c.topic, frame_id=m.header.frame_id,
                                 header_seq=m.header.seq, bag_timestamp_ns=bag_time,
                                 header_stamp_ns=m.header.stamp.sec*10**9+m.header.stamp.nanosec, **stats))
    if len(metadata) < 5:
        raise ValueError('At least five frames are required to estimate and validate the pattern')
    return np.stack(azs), np.stack(els), np.stack(counts), metadata


def fit_pattern(observed_az, observed_el, min_frames=3, max_az_mad=.15, max_el_mad=.20):
    """Fill within each half-FOV first, then between rings and handbook anchors."""
    ideal_az, ideal_el = ideal_grid()
    count = np.isfinite(observed_az).sum(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # all-NaN cells are intentionally missing
        med_az, med_el = np.nanmedian(observed_az, axis=0), np.nanmedian(observed_el, axis=0)
        mad_az = np.nanmedian(np.abs(observed_az-med_az), axis=0)
        mad_el = np.nanmedian(np.abs(observed_el-med_el), axis=0)
    reliable = (count >= min_frames) & (mad_az <= max_az_mad) & (mad_el <= max_el_mad)
    az, el = np.where(reliable, med_az, np.nan), np.where(reliable, med_el, np.nan)
    source = np.full((ROWS, COLS), 255, dtype=np.uint8)
    source[reliable] = 0
    # Horizontal interpolation never crosses the observed left/right seam.
    for row in range(ROWS):
        for start, stop in ((0, 240), (240, 480)):
            good = np.flatnonzero(reliable[row, start:stop]) + start
            if not len(good):
                continue
            missing = np.arange(start, stop)[~reliable[row, start:stop]]
            az[row, missing] = ideal_az[row, missing] + np.interp(
                missing, good, az[row, good]-ideal_az[row, good])
            el[row, missing] = np.interp(missing, good, el[row, good])
            source[row, missing] = np.where((missing > good[0]) & (missing < good[-1]), 1, 2)
    # The outer ideal cell centres are handbook anchors, not claimed observations.
    for row in (0, ROWS-1):
        missing = ~np.isfinite(el[row])
        az[row, missing], el[row, missing] = ideal_az[row, missing], ideal_el[row, missing]
        source[row, missing] = 4
    for col in range(COLS):
        good = np.flatnonzero(np.isfinite(el[:, col]))
        missing = np.flatnonzero(~np.isfinite(el[:, col]))
        if len(good) > 2:
            az[missing, col] = ideal_az[missing, col] + np.interp(
                missing, good, az[good, col]-ideal_az[good, col])
            el[missing, col] = np.interp(missing, good, el[good, col])
            source[missing, col] = 3
        else:
            az[missing, col], el[missing, col] = ideal_az[missing, col], ideal_el[missing, col]
            source[missing, col] = 4
    # An unobserved sector endpoint uses the handbook bin centre. Extending a
    # +0.25deg phase correction to 0- can otherwise duplicate a measured 0+ ray.
    for col in (0, 239, 240, COLS-1):
        inferred = source[:, col] != 0
        az[inferred, col] = ideal_az[inferred, col]
    return dict(azimuth_deg=az.astype(np.float32), elevation_deg=el.astype(np.float32),
                directions=directions(az, el).astype(np.float32), source=source,
                observation_frames=count.astype(np.uint16), observed_azimuth_deg=med_az,
                observed_elevation_deg=med_el, azimuth_mad_deg=mad_az, elevation_mad_deg=mad_el,
                ring=np.broadcast_to(np.arange(ROWS)[:, None], (ROWS, COLS)).astype(np.uint16),
                column=np.broadcast_to(np.arange(COLS), (ROWS, COLS)).astype(np.uint16))


def angle_error(a1, e1, a2, e2):
    # atan2 of cross/dot is stable for sub-millidegree differences.
    u, v = directions(a1, e1), directions(a2, e2)
    return np.degrees(np.arctan2(np.linalg.norm(np.cross(u, v), axis=-1), np.sum(u*v, axis=-1)))


def error_stats(error):
    error = np.asarray(error)
    return dict(count=int(error.size), mean_deg=float(error.mean()),
                p50_deg=float(np.quantile(error, .5)), p95_deg=float(np.quantile(error, .95)),
                p99_deg=float(np.quantile(error, .99)), max_deg=float(error.max()))


def validate_pattern(table):
    a, e, d = table['azimuth_deg'], table['elevation_deg'], table['directions']
    if a.shape != (ROWS, COLS) or e.shape != a.shape:
        raise AssertionError('Wrong 96x480 layout')
    assert np.isfinite(a).all() and np.isfinite(e).all() and np.isfinite(d).all()
    assert a.min() >= -120 and a.max() < 120 and e.min() >= -40 and e.max() <= 40
    assert (np.diff(a, axis=1) > 0).all(), 'Columns must be ordered without duplicated directions'
    assert (np.diff(e, axis=0) > 0).all(), 'Vertical channels must remain ordered'
    assert np.allclose(np.linalg.norm(d, axis=-1), 1, atol=1e-6)
    assert np.isin(table['source'], list(SOURCE_NAMES)).all()
    assert len(np.unique(np.round(d.reshape(-1, 3), 7), axis=0)) == ROWS*COLS
    return dict(passed=True, rays=ROWS*COLS, shape=[ROWS, COLS],
                azimuth_centres_deg=[float(a.min()), float(a.max())],
                elevation_centres_deg=[float(e.min()), float(e.max())],
                nominal_cell_coverage_deg=[H_FOV, V_FOV],
                unique_directions=ROWS*COLS,
                sources={name:int((table['source'] == code).sum()) for code, name in SOURCE_NAMES.items()})
