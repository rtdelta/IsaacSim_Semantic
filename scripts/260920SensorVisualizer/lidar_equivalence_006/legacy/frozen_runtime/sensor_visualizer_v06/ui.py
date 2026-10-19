"""ASCII controls; all stage writes dispatched at a complete group boundary."""
import asyncio
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import math
import traceback
import omni.ui as ui
from .contracts import load_job, write_json
from .coordinator import CaptureRunner
from .scene import SceneStepper
from .diagnostics import RunDiagnostics


class CapturePanel:
    def __init__(self,project):
        self.project=Path(project); self.scene=None; self.runner=None; self.task=None
        self.closed=False; self.busy=False; self.rows={}; self.joint_drafts={}; self.tilt_drafts={}
        self.job=load_job(overrides={'mode':'interactive','preview':{'enabled':True}})
        self.diag=RunDiagnostics(self.job['output_directory'],self.job['diagnostics'],self.project)
        self.diag.start_resources()
        import omni.kit.app
        self.diag.attach_kit(omni.kit.app.get_app())
        self.diag.context(phase='panel_idle')
        self.closing=False
        self.window=ui.Window('Sensor Visualizer v06',width=760,height=850)
        self.window.set_visibility_changed_fn(self._visibility)
        with self.window.frame:
            with ui.VStack(spacing=5):
                self.status=ui.Label('Open combine stage, then Initialize. Do not press timeline Play.',height=38,word_wrap=True)
                with ui.ScrollingFrame():
                    with ui.VStack(spacing=5,height=0):
                        with ui.HStack(height=28):
                            ui.Button('Initialize Current Stage',clicked_fn=lambda:self._task(self.initialize()))
                            ui.Button('Close / Restore',clicked_fn=lambda:self._task(self.close()))
                        with ui.HStack(height=26):
                            ui.Label('Groups',width=65); self.groups=ui.SimpleIntModel(100); ui.IntField(model=self.groups,width=80)
                            ui.Label('Hz',width=30); self.hz=ui.SimpleFloatModel(10); ui.FloatField(model=self.hz,width=60)
                            self.mode=ui.ComboBox(0,'Interactive <=0.1x','Offline unrestricted',width=180)
                            self.preview=ui.SimpleBoolModel(True); ui.CheckBox(model=self.preview,width=20); ui.Label('ROS preview')
                        ui.Label('Capture selection (set before Initialize; blank = all)',height=20)
                        self.lidar_ids=self._text('LiDAR IDs','')
                        self.camera_ids=self._text('Camera IDs','')
                        with ui.HStack(height=30):
                            ui.Button('Start Capture',clicked_fn=lambda:self._task(self.capture()))
                            ui.Button('Pause',clicked_fn=self.pause)
                            ui.Button('Resume',clicked_fn=self.resume)
                            ui.Button('Stop + Drain',clicked_fn=self.stop)
                        self.details=ui.Frame(height=0)
                        self.job_path=self._text('Job JSON',str(self.project/'config/saved_job.json'))
                        with ui.HStack(height=28):
                            ui.Button('Save Job',clicked_fn=lambda:self._guard(self.save_job))
                            ui.Button('Load Job (before Init)',clicked_fn=lambda:self._task(self.load()))
                        ui.Label('Stop restores initial robot and LiDAR mounts. Save poses/job explicitly before stopping.',height=40,word_wrap=True)

    def _visibility(self,visible):
        if not visible and not self.closed: self._task(self.close())

    def _text(self,label,value):
        with ui.HStack(height=26):
            ui.Label(label,width=145); model=ui.SimpleStringModel(value); ui.StringField(model=model)
        return model

    def _float(self,label,value):
        ui.Label(label,width=50); model=ui.SimpleFloatModel(value); ui.FloatField(model=model,width=82)
        return model

    def _guard(self,fn):
        try:
            fn(); return True
        except Exception as exc:
            self.status.text=str(exc); self.diag.warning('ui_control_failed',str(exc))
            print('[SV06 UI] '+str(exc),flush=True)
            return False

    def _task(self,coro):
        task=asyncio.ensure_future(coro)
        def done(t):
            if not t.cancelled() and t.exception():
                self.diag.warning('ui_task_failed',str(t.exception()))
                self.status.text=str(t.exception()); traceback.print_exception(t.exception())
        task.add_done_callback(done)
        return task

    def active(self): return self.runner is not None and self.task is not None and not self.task.done()

    def _selection(self,value): return [s.strip() for s in value.split(',') if s.strip()] or None

    async def initialize(self):
        if self.busy or self.active() or self.closed or self.closing: return
        self.busy=True
        try:
            if self.scene: await self.scene.close()
            self.job=load_job(overrides={**self.job,'sample_hz':self.hz.as_float,'groups':self.groups.as_int,
                'sensors':{'lidar_ids':self._selection(self.lidar_ids.as_string),'camera_ids':self._selection(self.camera_ids.as_string)}})
            self.scene=SceneStepper(self.project,self.job,self.diag)
            self.status.text='Initializing assets, articulation and render products...'
            with self.diag.span('initialize'):
                await self.scene.initialize(open_scene=False)
            self.job['scene']=self.scene.stage.GetRootLayer().realPath
            self.build_details(); self.status.text='Ready. Start Capture; timeline is controlled automatically.'
        except Exception as exc:
            self.diag.warning('initialize_failed',str(exc))
            if self.scene: await self.scene.close()
            self.scene=None
            raise
        finally: self.busy=False

    def build_details(self):
        self.rows.clear(); self.joint_drafts={}; self.tilt_drafts={}
        with self.details:
            with ui.VStack(spacing=6,height=0):
                counts=self.scene.registry
                ui.Label(f"{len(counts['cameras'])} cameras / {len(counts['lidars'])} Instant LiDARs",height=22)
                with ui.CollapsableFrame('Joints and body tilt (degrees; speed degrees/s)',collapsed=False):
                    with ui.VStack(spacing=4,height=0):
                        for role,states in [('joints',self.scene.motion.controller.states),('tilt',self.scene.motion.base_controller.tilt.states)]:
                            for name,state in states.items(): self._motion_row(role,name,state)
                        ui.Label('Cab-track stays at its initial angle.',height=20)
                with ui.CollapsableFrame('Whole machine: world position / yaw / velocity',collapsed=True):
                    with ui.VStack(height=0):
                        c=self.scene.motion.base_controller
                        with ui.HStack(height=28):
                            self.base={k:self._float(k,v) for k,v in [('x',c.x),('y',c.y),('z',c.z),('yaw',math.degrees(c.heading))]}
                        with ui.HStack(height=28):
                            self.base['speed']=self._float('m/s',0); self.base['rate']=self._float('deg/s',0)
                        with ui.HStack(height=28):
                            ui.Button('Apply XYZ / Yaw',clicked_fn=self.apply_base)
                            ui.Button('Start Velocity',clicked_fn=self.velocity)
                            ui.Button('Hold Base',clicked_fn=lambda:self.command('hold base',lambda:self.scene.motion.command_base('hold')))
                with ui.CollapsableFrame('LiDAR mounts: parent-local pose',collapsed=True):
                    with ui.VStack(height=0):
                        self.mounts=self.scene.poses.snapshot()
                        self.mount_select=ui.ComboBox(0,*[p['id'] for p in self.mounts],height=28)
                        self.mount_select.model.add_item_changed_fn(lambda *_:self.load_mount())
                        with ui.HStack(height=28): self.mount_xyz=[self._float(k,0) for k in ('X','Y','Z')]
                        with ui.HStack(height=28): self.mount_rpy=[self._float(k,0) for k in ('RX','RY','RZ')]
                        self.mount_parent=ui.Label('',height=35,word_wrap=True)
                        with ui.HStack(height=28):
                            ui.Button('Apply at Next Boundary',clicked_fn=self.apply_mount)
                            ui.Button('Save Current Poses',clicked_fn=lambda:self.command('save mount poses',self.save_poses))
                            ui.Button('Reset Mounts',clicked_fn=lambda:self.command('reset mounts',lambda:self.scene.poses.reset('user')))
                        self.load_mount()

    def _motion_row(self,kind,name,state):
        ui.Label(name+f' (limits {state.minimum:.1f} .. {state.maximum:.1f})',height=22)
        row={}
        with ui.HStack(height=27):
            selected=('direct','target','periodic').index(state.mode) if state.running else 0
            row['mode']=ui.ComboBox(selected,'Direct','Target + speed','Periodic',width=150)
            row['target']=self._float('Target',state.target if state.running else state.angle); row['speed']=self._float('Speed',state.speed)
            ui.Button('Apply',clicked_fn=lambda:self.apply_motion(kind,name),width=65)
            ui.Button('Hold',clicked_fn=lambda:self.command('hold '+name,lambda:(self.scene.motion.command if kind=='joints' else self.scene.motion.command_tilt)('hold',name=name)),width=60)
        with ui.HStack(height=27):
            row['lower']=self._float('Lower',state.lower); row['upper']=self._float('Upper',state.upper)
            row['actual']=ui.Label(f'Actual {state.angle:.2f}')
        self.rows[(kind,name)]=row

    def command(self,description,fn):
        if not self.scene or self.busy or self.closed: return
        if self.active():
            self.runner.enqueue(description,fn); self.status.text='Queued: '+description
        else:
            self.diag.event('control_requested',control=description)
            if self._guard(fn): self.diag.event('control_applied',control=description)

    def apply_motion(self,kind,name):
        row=self.rows[(kind,name)]
        value={'mode':('direct','target','periodic')[row['mode'].model.get_item_value_model().as_int],
               **{k:row[k].as_float for k in ('target','speed','lower','upper')}}
        def apply():
            self.scene.apply_commands({kind:{name:value}})
            (self.joint_drafts if kind=='joints' else self.tilt_drafts)[name]=value
        self.command('apply '+name,apply)

    def apply_base(self):
        values={k:self.base[k].as_float for k in ('x','y','z')}; values['yaw_deg']=self.base['yaw'].as_float
        self.command('base pose',lambda:self.scene.apply_commands({'base':values}))

    def velocity(self):
        speed=self.base['speed'].as_float; rate=self.base['rate'].as_float
        self.command('base velocity',lambda:self.scene.apply_commands({'base':{'speed_m_s':speed,'yaw_rate_deg_s':rate}}))

    def load_mount(self):
        index=self.mount_select.model.get_item_value_model().as_int
        row=self.scene.poses.snapshot()[index]
        for model,value in zip(self.mount_xyz+self.mount_rpy,row['position_m']+row['rotation_deg']): model.set_value(value)
        self.mount_parent.text=str(row.get('parent_path',row.get('reference','parent'))) + ' | metres / Kit Euler degrees'

    def apply_mount(self):
        row=self.scene.poses.snapshot()[self.mount_select.model.get_item_value_model().as_int]
        xyz=[m.as_float for m in self.mount_xyz]; rpy=[m.as_float for m in self.mount_rpy]
        self.command('mount '+row['id'],lambda:self.scene.poses.apply(row['id'],xyz,rpy,
            recording=str(self.runner.session) if self.active() else None))

    def save_poses(self): self.status.text='Saved poses: '+str(self.scene.poses.save())

    def update(self,runner):
        written=runner.pipeline.written if runner.pipeline else 0
        self.status.text=f'{runner.phase} | acquired {runner.groups} / written {written} | pending {runner.pending} | {runner.session}'
        for (kind,name),row in self.rows.items():
            states=self.scene.motion.controller.states if kind=='joints' else self.scene.motion.base_controller.tilt.states
            row['actual'].text=f'Actual {states[name].angle:.2f}'

    async def capture(self):
        if self.busy or self.active() or self.closed or self.closing: return
        if not self.scene or self.scene.drivers is None: raise RuntimeError('Initialize first')
        if self.scene.capture_failed or self.scene.invalid: raise RuntimeError('Previous capture or stage failed; Initialize again')
        mode=('interactive','offline')[self.mode.model.get_item_value_model().as_int]
        if self.hz.as_float!=self.job['sample_hz']: raise ValueError('Sample rate changed; Initialize again')
        self.job=load_job(overrides={**self.job,'mode':mode,'groups':self.groups.as_int,'preview':{**self.job['preview'],'enabled':self.preview.as_bool},'motion':{'joints':{},'tilt':{},'base':{}}})
        self.runner=CaptureRunner(self.project,self.job,self.scene,self.diag); self.runner.on_update=self.update
        self.task=asyncio.current_task()
        await self.runner.run()
        if not self.scene.invalid:
            self.scene.poses.reset('capture_stopped')
            self.scene.motion.controller.reset(); self.scene.motion.base_controller.reset()
            self.scene.motion._apply_controlled_base(self.scene.motion._command_angles())
        self.status.text=f'{self.runner.phase}. Output: {self.runner.session}. '+('Initialize again before retry.' if self.runner.error else 'Initial poses restored.')
        self.scene.on_phase=None
        self.diag.context(phase='idle',capture_id=None,group_id=None,request_id=None,attempt_id=None)

    def pause(self):
        if self.active(): self.runner.pause(); self.status.text='Pause requested; finishing current group.'
    def resume(self):
        if self.active(): self.runner.resume()
    def stop(self):
        if self.active(): self.runner.stop(); self.status.text='Finishing current group and draining MCAP...'

    def save_job(self):
        if not self.scene or self.busy: raise RuntimeError('Initialize first')
        if self.active():
            self.runner.enqueue('save job',self._save_job_now)
        else: self._save_job_now()

    def _save_job_now(self):
        job=deepcopy(self.job); job.update(mode='offline',groups=self.groups.as_int)
        c=self.scene.motion.base_controller
        job['motion']={'joints':deepcopy(self.joint_drafts),'tilt':deepcopy(self.tilt_drafts),
            'base':{'x':c.x,'y':c.y,'z':c.z,'yaw_deg':math.degrees(c.heading),'speed_m_s':c.speed,'yaw_rate_deg_s':math.degrees(c.yaw_rate)}}
        job['motion']['_initial']={}
        for kind,controller in (('joints',self.scene.motion.controller),('tilt',c.tilt)):
            job['motion']['_initial'][kind]={n:s.angle for n,s in controller.states.items()}
            job['motion']['_initial'][kind+'_directions']={n:s.direction for n,s in controller.states.items()}
        # Serialize authoritative controller state, including loaded jobs/events.
        # UI drafts alone miss a running command that did not originate in a row.
        for kind,controller in (('joints',self.scene.motion.controller),('tilt',c.tilt)):
            job['motion'][kind]={}
            for name,state in controller.states.items():
                if not state.running: command={'mode':'direct','target':state.angle}
                elif state.mode=='target': command={'mode':'target','target':state.target,'speed':state.speed}
                else: command={'mode':'periodic','lower':state.lower,'upper':state.upper,'speed':state.speed}
                job['motion'][kind][name]=command
        job['mount_poses']={p['id']:{k:p[k] for k in ('position_m','rotation_deg')} for p in self.scene.poses.snapshot() if p['editable']}
        path=Path(self.job_path.as_string); write_json(path,load_job(overrides=job)); self.status.text='Saved job: '+str(path)

    async def load(self):
        if self.busy or self.closed or self.closing:return
        self.busy=True
        try:
            if self.scene: raise RuntimeError('Close/reopen panel before loading another job')
            new_job=load_job(self.job_path.as_string)
            self.diag.detach_kit(); await asyncio.to_thread(self.diag.close)
            self.diag=RunDiagnostics(new_job['output_directory'],new_job['diagnostics'],self.project)
            self.diag.start_resources()
            import omni.kit.app
            self.diag.attach_kit(omni.kit.app.get_app())
            self.job=new_job; self.groups.set_value(self.job['groups']); self.hz.set_value(self.job['sample_hz'])
            self.mode.model.get_item_value_model().set_value(0 if self.job['mode']=='interactive' else 1)
            self.preview.set_value(self.job['preview']['enabled'])
            self.lidar_ids.set_value(','.join(self.job['sensors']['lidar_ids'] or [])); self.camera_ids.set_value(','.join(self.job['sensors']['camera_ids'] or []))
            self.status.text='Loaded job. Open its scene and Initialize.'
        finally:self.busy=False

    async def close(self):
        if self.closed or self.closing: return
        self.closing=True
        if self.busy:
            self.status.text='Closing after initialization completes...'
            while self.busy: await asyncio.sleep(.05)
        self.closed=True
        if self.active(): self.runner.stop(); await self.task
        try:
            if self.scene: await self.scene.close()
        finally:
            self.diag.detach_kit()
            await asyncio.to_thread(self.diag.close)
            self.window.visible=False
