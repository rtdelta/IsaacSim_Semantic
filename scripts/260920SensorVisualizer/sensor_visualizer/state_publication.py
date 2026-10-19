"""Publish sampled native DOFs and the same runtime root frame used by TF."""
import json
import math
import uuid

_instances = {}


def ros_stamp(seconds):
    total = round(float(seconds) * 1_000_000_000)
    return divmod(total, 1_000_000_000)


class SampleGate:
    def __init__(self, hz):
        if not math.isfinite(hz) or hz <= 0:
            raise ValueError('State publication rate must be finite and positive')
        self.period, self.last = 1 / hz, None

    def accept(self, stamp):
        if self.last is not None and stamp < self.last - 1e-8:
            self.last = None
        if self.last is not None and stamp - self.last < self.period - 1e-8:
            return False
        self.last = stamp
        return True


def tick(key):
    obj = _instances.get(key)
    return obj.sample() if obj else False


class StatePublication:
    def __init__(self, runtime):
        self.runtime = runtime
        self.key = uuid.uuid4().hex
        self.gate = SampleGate(float(runtime.config['state_publication']['rate_hz']))
        self.count = 0
        self.last_snapshot = None
        self.paths = {}

    async def build(self, graph_path):
        import omni.graph.core as og
        from pxr import Usd
        cfg = self.runtime.config['state_publication']
        if cfg['joint_topic'] == cfg['root_pose_topic']:
            raise ValueError('State topics must be distinct')
        nodes, values, connections = [], [], []
        for name, package, message, topic in [('JointStates', 'sensor_msgs', 'JointState', cfg['joint_topic']),
                ('RootPoseMessage', 'geometry_msgs', 'PoseStamped', cfg['root_pose_topic'])]:
            nodes.append((name, 'isaacsim.ros2.bridge.ROS2Publisher'))
            self.paths[name] = graph_path + '/' + name
            values.extend([(name + '.inputs:messagePackage', package),
                (name + '.inputs:messageSubfolder', 'msg'), (name + '.inputs:messageName', message),
                (name + '.inputs:topicName', topic), (name + '.inputs:qosProfile', json.dumps({
                    'history': 'keepLast', 'depth': 20, 'reliability': 'reliable', 'durability': 'volatile',
                    'deadline': 0.0, 'lifespan': 0.0, 'liveliness': 'systemDefault', 'leaseDuration': 0.0}))])
            connections.extend([('StateSample.outputs:execOut', name + '.inputs:execIn'),
                                ('Context.outputs:context', name + '.inputs:context')])
        nodes.append(('StateSample', 'omni.graph.scriptnode.ScriptNode'))
        values.append(('StateSample.inputs:script',
            'import omni.graph.core as og\nfrom sensor_visualizer.state_publication import tick\n'
            'def compute(db):\n'
            f'    db.outputs.execOut = og.ExecutionAttributeState.ENABLED if tick({self.key!r}) else og.ExecutionAttributeState.DISABLED\n'
            '    return True\n'))
        connections.append(('Motion.outputs:execOut', 'StateSample.inputs:execIn'))
        connections = [(graph_path + '/' + a, graph_path + '/' + b) for a, b in connections]
        with Usd.EditContext(self.runtime.stage, self.runtime.layer):
            og.Controller.edit(og.get_graph_by_path(graph_path), {
                og.Controller.Keys.CREATE_NODES: nodes, og.Controller.Keys.SET_VALUES: values,
                og.Controller.Keys.CONNECT: connections})
        for _ in range(8):
            await self.runtime.app.next_update_async()
            if all(og.Controller.attribute(p + '.inputs:header:stamp:sec').is_valid() for p in self.paths.values()):
                break
        else:
            raise RuntimeError('ROS generic publishers did not expose stamped message fields')
        _instances[self.key] = self

    def sample(self):
        import omni.graph.core as og
        from pxr import Usd
        row = self.runtime.motion.last_snapshot
        if row is None or not self.gate.accept(row['time']):
            return False
        sec, ns = ros_stamp(row['time'])
        with Usd.EditContext(self.runtime.stage, self.runtime.layer):
            def put(node, field, value):
                og.Controller.set(og.Controller.attribute(self.paths[node] + '.inputs:' + field), value)
            for node in self.paths:
                put(node, 'header:stamp:sec', sec)
                put(node, 'header:stamp:nanosec', ns)
                put(node, 'header:frame_id', self.runtime.config['world_frame'] if node == 'RootPoseMessage' else '')
            put('JointStates', 'name', row['names'])
            put('JointStates', 'position', row['positions'])
            put('JointStates', 'velocity', [])
            put('JointStates', 'effort', [])
            for axis, value in zip('xyz', row['root_position']):
                put('RootPoseMessage', 'pose:position:' + axis, value)
            for axis, value in zip('xyzw', row['root_xyzw']):
                put('RootPoseMessage', 'pose:orientation:' + axis, value)
        self.count += 1
        self.last_snapshot = row
        return True

    def close(self):
        _instances.pop(self.key, None)
