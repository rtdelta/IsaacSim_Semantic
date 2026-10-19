"""Small native control panel; movement is queued for the next physical step."""
import json


class Panel:
    def __init__(self,owner,recording):
        import omni.ui as ui
        self.owner,self.recording=owner,recording
        self.window=ui.Window('single0601ContinuousRt',width=360,height=340)
        with self.window.frame:
            with ui.VStack(spacing=6):
                self.status=ui.Label('Preparing verified sensor backend')
                ui.Label('Viewport keys: W/S A/D Q/E; R/F height; U/O T/G Y/H joints')
                with ui.HStack():
                    ui.Label('Speed m/s')
                    self.speed=ui.FloatField()
                    self.speed.model.set_value(.3)
                with ui.HStack():
                    ui.Label('Yaw deg/s')
                    self.yaw=ui.FloatField()
                    self.yaw.model.set_value(3.)
                ui.Button('Apply velocity',clicked_fn=self.apply)
                ui.Button('Hold movement',clicked_fn=lambda:owner.controller.enqueue('parameters','hold'))
                ui.Label('Trajectory JSON: [[simulation_s,x_m,y_m,yaw_deg], ...]')
                self.trajectory=ui.StringField()
                self.trajectory.model.set_value('[[0,0,0,0],[4,1,0,10]]')
                ui.Button('Apply trajectory',clicked_fn=self.apply_trajectory)
                with ui.HStack():
                    ui.Button('Pause after current group',clicked_fn=lambda:self.pause(True))
                    ui.Button('Resume',clicked_fn=lambda:self.pause(False))
                ui.Button('Stop after current group',clicked_fn=self.stop)

    def apply(self):
        self.owner.controller.enqueue('parameters','base_velocity',{'speed_m_s':self.speed.model.as_float,'yaw_rate_deg_s':self.yaw.model.as_float})

    def apply_trajectory(self):
        try:
            points=json.loads(self.trajectory.model.as_string)
            self.owner.controller.enqueue('trajectory','trajectory',{'waypoints':points})
        except (ValueError,TypeError):
            self.status.text='Invalid trajectory JSON'

    def pause(self,paused):
        self.recording.request_pause=paused
        self.owner.native_keyboard.clear('pause')

    def stop(self):
        self.recording.request_stop=True
        self.owner.native_keyboard.clear('stop')

    def progress(self,written,requested,backend):
        self.status.text='%s: %s / %s written'%(backend,written,requested)

    def close(self):
        self.window.visible=False
        self.window=None
