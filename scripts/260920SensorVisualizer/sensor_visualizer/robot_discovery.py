"""Discover articulated excavators from body relationships, preserving native angles."""
from copy import deepcopy

ROLES = ('swing', 'boom', 'arm', 'bucket')
ALIASES = {'swing': 'track_operator_cab_joint', 'boom': 'platform_boom_joint',
           'arm': 'boom_small_arm_joint', 'bucket': 'small_arm_bucket_joint'}


def chains_from_records(roots, joints):
    """Find directed four-joint chains; reject branches, cycles and extra DOFs."""
    result = []
    for root in roots:
        base = root['base_body']
        chain, visited, current = [], {base}, base
        while True:
            edges = [j for j in joints if j['body0'] == current]
            if not edges:
                break
            if len(edges) != 1 or edges[0]['body1'] in visited:
                chain = []
                break
            joint = edges[0]
            chain.append(joint)
            current = joint['body1']
            visited.add(current)
        if len(chain) != 4 or any(j.get('enabled') is False for j in chain):
            continue
        if any(j['body1'] in visited and j not in chain for j in joints):
            continue
        item = dict(root, joints={role: dict(j) for role, j in zip(ROLES, chain)})
        names = [j['name'] for j in chain]
        item['naming_profile'] = ('urdf_names' if names == list(ROLES) else
                                  'legacy_names' if names == [ALIASES[r] for r in ROLES] else 'unrecognized')
        # An arbitrary four-axis robot is not assumed to be an excavator.
        item['auto_eligible'] = item['naming_profile'] != 'unrecognized'
        item['angle_convention'] = 'Native asset DOF angles; no zero/sign conversion'
        result.append(item)
    return sorted(result, key=lambda x: x['articulation_root'])


def discover_robots(stage):
    from pxr import UsdPhysics
    joints, roots = [], []
    for prim in stage.Traverse():
        if prim.IsA(UsdPhysics.RevoluteJoint):
            joint = UsdPhysics.Joint(prim)
            a, b = joint.GetBody0Rel().GetTargets(), joint.GetBody1Rel().GetTargets()
            if len(a) == len(b) == 1:
                joints.append({'path': str(prim.GetPath()), 'name': prim.GetName(),
                    'body0': str(a[0]), 'body1': str(b[0]),
                    'enabled': joint.GetJointEnabledAttr().Get(),
                    'axis': str(UsdPhysics.RevoluteJoint(prim).GetAxisAttr().Get()),
                    'local_pos0': list(joint.GetLocalPos0Attr().Get()),
                    'local_rot0': str(joint.GetLocalRot0Attr().Get()),
                    'native_metadata': str(prim.GetCustomData())})
    for prim in stage.Traverse():
        if not prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            continue
        base = str(prim.GetPath())
        if prim.IsA(UsdPhysics.FixedJoint):
            joint = UsdPhysics.Joint(prim)
            targets = joint.GetBody0Rel().GetTargets() + joint.GetBody1Rel().GetTargets()
            if len(targets) != 1:
                continue
            base = str(targets[0])
        elif not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            local = [j for j in joints if j['body0'].startswith(base + '/')]
            starts = set(j['body0'] for j in local) - set(j['body1'] for j in local)
            if len(starts) != 1:
                continue
            base = starts.pop()
        # Common body ancestor is the model container, not the stage filename.
        connected = [base]
        cursor = base
        for _ in range(4):
            edges = [j for j in joints if j['body0'] == cursor]
            if len(edges) != 1:
                break
            cursor = edges[0]['body1']; connected.append(cursor)
        from posixpath import commonpath
        model = commonpath(connected)
        if model == base or model == '/':
            continue
        roots.append({'robot_prim': model, 'articulation_root': str(prim.GetPath()),
                      'base_body': base, 'stage': stage.GetRootLayer().identifier})
    return chains_from_records(roots, joints)


def bind_config(config, candidate):
    resolved = deepcopy(config)
    old = resolved.get('robot_motion', {})
    speeds = resolved.get('joint_speeds_deg_s', {'boom': 5., 'arm': 4., 'bucket': 10 / 3})
    resolved['robot_binding'] = deepcopy(candidate)
    resolved['robot_motion'] = dict(old, enabled=True, robot_prim=candidate['robot_prim'],
        articulation_root=candidate['articulation_root'], base_body=candidate['base_body'],
        fixed_joint=candidate['joints']['swing']['name'],
        forward_speed_m_s=old.get('forward_speed_m_s', 0),
        joints=[{'name': candidate['joints'][r]['name'], 'role': r,
                 'speed_deg_s': speeds.get(r, 5.)} for r in ROLES[1:]])
    resolved['state_publication']['joint_names'] = [candidate['joints'][r]['name'] for r in ROLES]
    return resolved
