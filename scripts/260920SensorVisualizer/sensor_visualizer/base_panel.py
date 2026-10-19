"""Whole excavator control and fisheye capture controls."""
import math
import omni.ui as ui


class BasePanel:
    def __init__(self,runtime):
        self.runtime=runtime
        self.bound=None
        self.models={}
        self.label=ui.Label('Press Play once to initialize base controls',height=22)
        with ui.VStack(height=0,spacing=5) as controls:
            with ui.HStack(height=25,spacing=4):
                for name,label,value in [('x','World X (m)',0),('y','World Y (m)',0),('yaw_deg','Heading (deg)',0)]:
                    ui.Label(label,width=95)
                    self.models[name]=ui.SimpleFloatModel(value)
                    ui.FloatField(model=self.models[name],width=90)
                ui.Button('Apply Pose',clicked_fn=lambda:self.command('direct'))
            with ui.HStack(height=25,spacing=4):
                ui.Label('World Z (m)',width=110)
                self.models['z']=ui.SimpleFloatModel(0)
                ui.FloatField(model=self.models['z'],width=90)
                ui.Button('Apply Height',clicked_fn=lambda:self.command('height'))
            with ui.HStack(height=25,spacing=4):
                for name,label,value in [('speed','Speed (m/s)',0.1),('yaw_rate_deg','Yaw rate (deg/s)',0)]:
                    ui.Label(label,width=110)
                    self.models[name]=ui.SimpleFloatModel(value)
                    ui.FloatField(model=self.models[name],width=90)
                ui.Button('Start Move',clicked_fn=lambda:self.command('velocity'))
                ui.Button('Hold Base',clicked_fn=lambda:self.command('hold'))
                ui.Button('Reset Base',clicked_fn=lambda:self.command('reset'))
            from .tilt_panel import TiltPanel
            self.tilt_panel=TiltPanel(self)
        self.controls=controls
        ui.Label('Negative speed = reverse. World Z is the robot reference height. No automatic ground following.',height=30,word_wrap=True)
        self.refresh()

    def command(self,action):
        try:
            if not self.available():
                raise ValueError('Base control requires Play/Pause and no LiDAR adjustment')
            keys={'direct':('x','y','yaw_deg'),'height':('z',),'velocity':('speed','yaw_rate_deg')}.get(action,())
            self.runtime.motion.command_base(action,**{k:self.models[k].as_float for k in keys})
            self.runtime.set_status('Base: '+action)
        except Exception as exc:
            self.runtime.set_status(str(exc))
        self.refresh()

    def available(self):
        r=self.runtime
        return (not r.closed and not r.closing and r.pose_state=='idle' and r.motion and
                r.motion.ready and not r.timeline.is_stopped() and r.motion.mode=='scripted')

    def refresh(self):
        self.controls.enabled=bool(self.available())
        motion=self.runtime.motion
        c=motion.base_controller if motion else None
        if c:
            if self.bound is not c:
                self.bound=c
                for k,v in [('x',c.x),('y',c.y),('z',c.z),('yaw_deg',math.degrees(c.heading))]:
                    self.models[k].set_value(v)
            self.label.text=f'Base X={c.x:.3f}, Y={c.y:.3f}, Z={c.z:.3f}, heading={math.degrees(c.heading):.2f} deg | v={c.speed:.3f} m/s'
        self.tilt_panel.refresh()


class CameraPanel:
    def __init__(self,runtime):
        self.runtime=runtime
        self.ids=list(runtime.camera.cameras) if hasattr(runtime.camera,'cameras') else []
        with ui.HStack(height=27,spacing=5):
            if self.ids:
                self.selection=ui.ComboBox(0,*[x.title() for x in self.ids],width=130)
            ui.Button('Open Camera View',clicked_fn=lambda:self.run(self.preview))
            ui.Button('Save All Camera Snapshot' if self.ids else 'Save Image Snapshot',
                      clicked_fn=lambda:self.run(runtime.camera.snapshot))
        ui.Label('Start/Stop Recording saves LiDAR MCAP + fisheye PNG/JSONL in one session.',height=22)
        self.label=ui.Label('',height=25)
        self.refresh()

    def preview(self):
        if self.ids:
            return self.runtime.camera.preview(self.ids[self.selection.model.get_item_value_model().as_int])
        return self.runtime.camera.preview()

    def run(self,fn):
        try:
            result=fn()
            if result: self.runtime.set_status(str(result))
        except Exception as exc:
            self.runtime.set_status(str(exc))

    def refresh(self):
        c=self.runtime.camera
        if self.ids:
            self.label.text=f'{len(self.ids)} cameras | Saved groups: {c.count} | Unmatched images: {c.unmatched} | Recording: {bool(c.stream)}'
        else:
            self.label.text=f'Fisheye: {c.received} rendered / {c.unmatched} unmatched | Saved: {c.count} | Recording: {bool(c.stream)}'
