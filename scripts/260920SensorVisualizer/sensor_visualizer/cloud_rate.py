"""Timestamp gate placed immediately before each native ROS point-cloud writer."""
import math
import uuid

_gates = {}


def on_capture_grid(timestamp, rate_hz):
    """Shared zero-epoch cadence; rates must divide the fixed simulation rate."""
    phase = timestamp * rate_hz
    return timestamp > 1e-8 and abs(phase-round(phase)) < 1e-5


def prune_invalid_sdg_handles():
    """6.0.1 compatibility: forget destroyed graph handles, retaining live owners.

    SyntheticData._get_or_create_graph otherwise returns a cached invalid
    Py_Graph after legacy persisted render graphs are recomposed. Its public
    reset would also discard unrelated live camera/annotator state.
    """
    from omni.syntheticdata import SyntheticData
    sd = SyntheticData.Get()
    graphs = getattr(sd, '_nodeGraphs', {})
    dead = []
    for path, node in list(graphs.items()):
        try:
            valid = node.is_valid() and node.get_wrapped_graph().is_valid()
        except ValueError:
            valid = False
        if not valid:
            dead.append(path)
            graphs.pop(path, None)
    nodes = getattr(sd, '_graphNodes', {})
    removed = set()
    for path, node in list(nodes.items()):
        if not node.is_valid() or any(path.startswith(graph + '/') for graph in dead):
            nodes.pop(path, None)
            removed.add(path)
    if removed:
        sd._activatedNodePaths[:] = [p for p in sd._activatedNodePaths if p not in removed]
    return dead


class ScanRateGate:
    def __init__(self, rate_hz):
        if not math.isfinite(rate_hz) or rate_hz <= 0:
            raise ValueError("LiDAR scan rate must be positive.")
        self.period = 1.0 / rate_hz
        self.reset()

    def reset(self):
        self.last_seen = self.last_published = None
        self.published = self.throttled = self.empty = 0

    def accept(self, timestamp, buffer_size):
        if not math.isfinite(timestamp):
            return False
        if self.last_seen is not None and timestamp < self.last_seen - 1e-7:
            self.reset()
        self.last_seen = timestamp
        if buffer_size <= 0:
            self.empty += 1
            return False
        if not on_capture_grid(timestamp, 1.0/self.period):
            self.throttled += 1
            return False
        if self.last_published is not None and timestamp - self.last_published < self.period - 1e-7:
            self.throttled += 1
            return False
        self.last_published = timestamp
        self.published += 1
        return True


def resolve_scan_rates(stage, sensors):
    for sensor in sensors:
        prim = stage.GetPrimAtPath(sensor["prim_path"])
        rate = float(prim.GetAttribute("omni:sensor:Core:scanRateBaseHz").Get() or 0)
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError(f"Invalid scanRateBaseHz on {sensor['prim_path']}")
        # Renderer accumulation owns complete scans. The gate never drops partial
        # pieces needed to assemble a rotary scan.
        sensor["publish_rate_hz"] = rate
        sensor["scan_type"] = str(prim.GetAttribute("omni:sensor:Core:scanType").Get())
        sensor["publish_policy"] = "instant_scan_zero_epoch_time_grid"


class CloudPublishers:
    def __init__(self):
        self.writers = []
        self.node_paths = []
        self.gate_nodes = {}
        self.original_exec = {}
        self.context_path = None
        self.gate_keys = {}
        self.stats = {}

    async def attach(self, runtime, qos):
        import omni.graph.core as og
        import omni.replicator.core as rep
        from omni.graph.tools import ogn
        from pxr import Usd
        prune_invalid_sdg_handles()
        with Usd.EditContext(runtime.stage, runtime.stage.GetSessionLayer()):
            for sensor, product in zip(runtime.config["sensors"], runtime.products):
                writer = rep.writers.get("RtxLidarROS2PublishPointCloud")
                writer.initialize(frameId=sensor["frame_id"], topicName=sensor["topic"],
                                  nodeNamespace="", context=0, queueSize=20, qosProfile=qos)
                self.writers.append(writer)
                writer.attach([product.path])
        # Attachment is asynchronous; remain paused until every gate is installed.
        for _ in range(8):
            await runtime.app.next_update_async()
            nodes = [node for graph in og.get_all_graphs() for node in graph.get_nodes()
                     if node.get_type_name() == "isaacsim.ros2.bridge.ROS2PublishPointCloud"]
            found = {s["id"]: [n for n in nodes if
                     og.Controller.get(n.get_attribute("inputs:topicName")) == s["topic"]
                     and og.Controller.get(n.get_attribute("inputs:frameId")) == s["frame_id"]]
                     for s in runtime.config["sensors"]}
            if all(len(v) == 1 for v in found.values()):
                break
        else:
            raise RuntimeError("Could not locate unique native point-cloud writers after attachment.")
        with Usd.EditContext(runtime.stage, runtime.stage.GetSessionLayer()):
            for sensor in runtime.config["sensors"]:
                node = found[sensor["id"]][0]
                upstream = list(node.get_attribute("inputs:execIn").get_upstream_connections())
                if len(upstream) != 1:
                    raise RuntimeError("Unexpected point-cloud writer execution wiring.")
                path = str(node.get_prim_path())
                if self.context_path is None:
                    self.context_path = path.rsplit("/", 1)[0] + "/LV_ROSContext_" + uuid.uuid4().hex
                    context_node = og.Controller.create_node(self.context_path, "isaacsim.ros2.bridge.ROS2Context")
                    og.Controller.set(context_node.get_attribute("inputs:domain_id"), runtime.config["ros_domain_id"])
                    og.Controller.set(context_node.get_attribute("inputs:useDomainIDEnvVar"), False)
                gate_path = path + "_LVRateGate"
                gate = og.Controller.create_node(gate_path, "omni.graph.scriptnode.ScriptNode")
                # ScriptNode normally auto-enables execOut after compute. Own
                # the output explicitly and push the on-demand SDG downstream.
                gate.get_attribute("outputs:execOut").set_metadata(ogn.MetadataKeys.HIDDEN, "1")
                self.node_paths.append(gate_path)
                self.gate_nodes[gate_path] = gate
                self.original_exec[gate_path] = (upstream[0].get_path(), node.get_attribute("inputs:execIn").get_path())
                for name, kind in [("timeStamp", og.BaseDataType.DOUBLE), ("bufferSize", og.BaseDataType.UINT)]:
                    og.Controller.create_attribute(gate, "inputs:" + name, og.Type(kind))
                    source = list(node.get_attribute("inputs:" + name).get_upstream_connections())
                    if len(source) != 1:
                        raise RuntimeError(f"Missing native cloud {name} input.")
                    og.Controller.connect(source[0], gate.get_attribute("inputs:" + name))
                    if name == "timeStamp":
                        og.Controller.set(source[0].get_node().get_attribute("inputs:resetOnStop"), True)
                key = uuid.uuid4().hex
                self.gate_keys[sensor["id"]] = key
                self.stats[sensor["id"]] = _gates[key] = ScanRateGate(sensor["publish_rate_hz"])
                script = (
                    "import omni.graph.core as og\n"
                    "from sensor_visualizer.cloud_rate import _gates\n"
                    "def compute(db):\n"
                    f"    gate = _gates.get({key!r})\n"
                    "    ok = gate is not None and gate.accept(db.inputs.timeStamp, db.inputs.bufferSize)\n"
                    "    db.outputs.execOut = og.ExecutionAttributeState.ENABLED_AND_PUSH if ok else og.ExecutionAttributeState.DISABLED\n"
                    "    return True\n"
                )
                og.Controller.set(gate.get_attribute("inputs:script"), script)
                og.Controller.disconnect(upstream[0], node.get_attribute("inputs:execIn"))
                og.Controller.connect(upstream[0], gate.get_attribute("inputs:execIn"))
                og.Controller.connect(gate.get_attribute("outputs:execOut"), node.get_attribute("inputs:execIn"))
                # Keep the render graph independent of the simulation ActionGraph.
                og.Controller.connect(self.context_path + ".outputs:context", node.get_attribute("inputs:context"))

    def reset(self):
        for gate in self.stats.values():
            gate.reset()

    def prepare_close(self):
        import omni.graph.core as og
        import omni.usd
        from omni.graph.scriptnode.ogn.python.nodes.OgnScriptNode import OgnScriptNode
        # NodeWriter detach can remove upstream nodes itself. Clean ScriptNodes
        # while their USD attributes still exist, before that recursive removal.
        stage = omni.usd.get_context().get_stage()
        if stage:
            for path in self.node_paths:
                node = self.gate_nodes[path]
                if node.is_valid():
                    source, destination = self.original_exec[path]
                    og.Controller.disconnect(node.get_attribute("outputs:execOut"), destination)
                    og.Controller.connect(source, destination)
                    OgnScriptNode.try_cleanup(node)
                    og.Controller.delete_node(node)
        self.node_paths.clear()
        self.gate_nodes.clear()
        self.original_exec.clear()

    async def close(self, app, same_stage=True):
        import omni.graph.core as og
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        if same_stage:
            self.prepare_close()
            for writer in self.writers:
                writer.detach()
            for _ in range(4):
                await app.next_update_async()
        # On stage replacement Replicator clears its old stage registry itself;
        # detaching against the replacement USD stage would target wrong nodes.
        if same_stage and stage and self.context_path and stage.GetPrimAtPath(self.context_path):
            og.Controller.delete_node(self.context_path)
        self.context_path = None
        for key in self.gate_keys.values():
            _gates.pop(key, None)
        self.writers.clear()
        self.node_paths.clear()
        self.gate_keys.clear()

    def prepare_stage_close(self):
        """Detach owned writers while their old USD/SDG graph still exists."""
        self.prepare_close()
        for writer in self.writers:
            writer.detach()
        self.writers.clear()
