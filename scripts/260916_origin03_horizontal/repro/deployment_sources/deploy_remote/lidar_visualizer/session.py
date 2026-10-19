"""GUI scene selection, rebuild and automatic binding across stage replacement."""
import asyncio
import builtins
from copy import deepcopy
import omni.kit.app
import omni.ui as ui
import omni.usd
from .config import load_config
from .robot_discovery import discover_robots, bind_config
from .runtime import LidarVisualizer


class SceneSession:
    def __init__(self, project_dir, config=None, artifact_dir=None, show_ui=True):
        self.project_dir, self.artifact_dir = project_dir, artifact_dir
        self.config = deepcopy(config) if config is not None else load_config(project_dir / 'config/sensors.json')
        self.context = omni.usd.get_context()
        self.app = omni.kit.app.get_app()
        self.instance = None
        self.window = None
        self.show_ui = show_ui
        self.candidates = []
        self.closed = False
        self.generation = 0
        self.task = None
        self.lock = asyncio.Lock()
        self.error = None
        self.mode = self.config.get('control_mode', 'scripted')
        self.subscription = self.context.get_stage_event_stream().create_subscription_to_pop(
            self._on_stage, name='Lidar Visualizer automatic scene binding')

    def _on_stage(self, event):
        if not self.closed and event.type == int(omni.usd.StageEventType.OPENED):
            self.request_rescan()

    def request_rescan(self, candidate=None, mode=None):
        if self.closed:
            return
        self.generation += 1
        generation = self.generation
        self.task = asyncio.ensure_future(self.refresh(candidate, mode, generation))
        return self.task

    async def refresh(self, candidate=None, mode=None, generation=None):
        async with self.lock:
            if self.closed or generation is not None and generation != self.generation:
                return
            self.error = None
            if mode:
                self.mode = mode
            try:
                if self.instance:
                    await self.instance.close()
                    self.instance = None
                    builtins._lidar_visualizer_instance = None
                stage = self.context.get_stage()
                if not stage:
                    self.candidates = []
                    self._window('Open a USD stage, then use Rescan.')
                    return
                for _ in range(300):
                    if self.context.get_stage_loading_status()[2] == 0:
                        break
                    await self.app.next_update_async()
                else:
                    raise RuntimeError('Assets are still loading. Use Rescan after loading completes.')
                if stage != self.context.get_stage() or self.closed or generation is not None and generation != self.generation:
                    return
                self.candidates = discover_robots(stage)
                choices = [c for c in self.candidates if c['articulation_root'] == candidate] if candidate else [c for c in self.candidates if c['auto_eligible']]
                if len(choices) != 1 or candidate is None and len(self.candidates) != 1:
                    self._window('Select an excavator and press Connect.' if self.candidates else
                                 'No supported four-joint articulation found. Load assets, then Rescan.')
                    return
                cfg = bind_config(self.config, choices[0])
                cfg['control_mode'] = self.mode
                self.instance = LidarVisualizer(self.project_dir, cfg, artifact_dir=self.artifact_dir)
                builtins._lidar_visualizer_instance = self.instance
                await self.instance.initialize(show_ui=self.show_ui)
                self._window('Connected. Play starts sampling; joints stay at their startup pose.')
            except Exception as exc:
                self.error = str(exc)
                if self.instance:
                    await self.instance.close()
                    self.instance = None
                    builtins._lidar_visualizer_instance = None
                self._window('Connection failed: ' + str(exc))
                print('[LidarVisualizer connection]', str(exc), flush=True)

    def _window(self, status):
        if not self.show_ui or self.closed:
            return
        if self.window:
            self.window.set_visibility_changed_fn(None)
            self.window.destroy()
        self.window = ui.Window('Excavator Connection', width=750, height=245)
        with self.window.frame:
            with ui.VStack(spacing=7):
                stage = self.context.get_stage()
                ui.Label('Stage: ' + (stage.GetRootLayer().identifier if stage else '(none)'), word_wrap=True, height=40)
                labels = [c['robot_prim'] + ' | ' + c['naming_profile'] for c in self.candidates] or ['No candidate']
                selected = next((i for i, c in enumerate(self.candidates) if self.instance and
                    c['articulation_root'] == self.instance.config['robot_motion']['articulation_root']), 0)
                self.robot_combo = ui.ComboBox(selected, *labels, height=25)
                self.mode_combo = ui.ComboBox(0 if self.mode == 'scripted' else 1,
                    'Scripted control + publish', 'Observe + publish (no motion writes)', height=25)
                with ui.HStack(height=28):
                    ui.Button('Connect / Apply mode', clicked_fn=self.connect_selected, enabled=bool(self.candidates))
                    ui.Button('Rescan current stage', clicked_fn=self.request_rescan)
                ui.Label(status, word_wrap=True, height=55)
        self.window.set_visibility_changed_fn(lambda visible: None if visible else self.request_close())

    def connect_selected(self):
        if not self.candidates:
            return
        idx = self.robot_combo.model.get_item_value_model().as_int
        mode = ('scripted', 'observe')[self.mode_combo.model.get_item_value_model().as_int]
        self.request_rescan(self.candidates[idx]['articulation_root'], mode)

    def request_close(self):
        asyncio.ensure_future(self.close())

    async def close(self):
        self.closed = True
        self.generation += 1
        self.subscription = None
        async with self.lock:
            if self.instance:
                await self.instance.close()
                if getattr(builtins, '_lidar_visualizer_instance', None) is self.instance:
                    builtins._lidar_visualizer_instance = None
                self.instance = None
            if self.window:
                self.window.set_visibility_changed_fn(None)
                self.window.destroy()
                self.window = None
