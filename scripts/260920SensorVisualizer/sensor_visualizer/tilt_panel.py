"""Pitch/roll controls use the same scalar motion modes as the arm joints."""
import omni.ui as ui
from .joint_control import MODES


class TiltPanel:
    def __init__(self, base_panel):
        self.base = base_panel
        self.rows = {}
        self.bound = None
        self.syncing = False
        ui.Label('Body tilt offsets from startup: Pitch (Y), Roll (X) | deg, deg/s', height=22)
        for name in ('pitch', 'roll'):
            row = {'readout': ui.Label(name.title()+' | waiting', height=21)}
            with ui.HStack(height=27, spacing=4):
                row['mode'] = ui.ComboBox(0, 'Direct set', 'Target + speed', 'Periodic', width=145)
                row['mode'].model.add_item_changed_fn(lambda _m, _i, n=name: self.select(n))
                ui.Label('Target', width=42)
                row['target'] = ui.SimpleFloatModel(0)
                row['target_field'] = ui.FloatField(model=row['target'], width=80)
                ui.Label('Speed', width=42)
                row['speed'] = ui.SimpleFloatModel(5)
                row['speed_field'] = ui.FloatField(model=row['speed'], width=80)
                row['go'] = ui.Button('Apply', clicked_fn=lambda n=name: self.execute(n))
                ui.Button('Hold', clicked_fn=lambda n=name: self.run('hold', name=n), width=65)
            with ui.HStack(height=25, spacing=4) as bounds:
                ui.Label('Periodic limits', width=145)
                ui.Label('Lower', width=42)
                row['lower'] = ui.SimpleFloatModel(-15)
                ui.FloatField(model=row['lower'], width=80)
                ui.Label('Upper', width=42)
                row['upper'] = ui.SimpleFloatModel(15)
                ui.FloatField(model=row['upper'], width=80)
                row['limits'] = ui.Label('')
            row['bounds'] = bounds
            self.rows[name] = row
        with ui.HStack(height=28, spacing=6):
            ui.Button('Start Both Tilts', clicked_fn=self.execute_all)
            ui.Button('Hold Both Tilts', clicked_fn=lambda: self.run('hold'))
        ui.Label('Zero = startup tilt. Hold Base stops all base motion; Reset Base restores XYZ and orientation.',
                 height=32, word_wrap=True)

    def mode(self, name):
        return MODES[self.rows[name]['mode'].model.get_item_value_model().as_int]

    def draft(self, name):
        row = self.rows[name]
        return dict(mode=self.mode(name), **{k: row[k].as_float for k in ('target','speed','lower','upper')})

    def select(self, name):
        if not self.syncing:
            self.run('mode', name=name, mode=self.mode(name))

    def run(self, action, **values):
        try:
            if not self.base.available():
                raise ValueError('Play once before using tilt controls')
            self.base.runtime.motion.command_tilt(action, **values)
            self.base.runtime.set_status('Tilt command accepted. Target/Periodic motion advances while playing.')
        except Exception as exc:
            self.base.runtime.set_status(str(exc))
        self.refresh()

    def execute(self, name):
        self.run('execute', commands={name: self.draft(name)})

    def execute_all(self):
        commands = {n: self.draft(n) for n in self.rows if self.mode(n) != 'direct'}
        if commands:
            self.run('execute', commands=commands)
        else:
            self.base.runtime.set_status('Start Both Tilts uses Target/Periodic rows. Direct set uses each Apply.')

    def refresh(self):
        motion = self.base.runtime.motion
        c = motion.base_controller if motion else None
        if c and self.bound is not c:
            self.syncing = True
            for name, row in self.rows.items():
                s = c.tilt.states[name]
                for key in ('target','speed','lower','upper'):
                    row[key].set_value(getattr(s,key))
                row['mode'].model.get_item_value_model().set_value(MODES.index(s.mode))
                row['limits'].text = f'Offset range: {s.minimum:.1f} .. {s.maximum:.1f}'
            self.syncing = False
            self.bound = c
        for name, row in self.rows.items():
            mode = self.mode(name)
            row['bounds'].enabled = mode == 'periodic'
            row['target_field'].enabled = mode != 'periodic'
            row['speed_field'].enabled = mode != 'direct'
            row['go'].text = 'Apply' if mode == 'direct' else 'Start'
            if c:
                s = c.tilt.states[name]
                status = ('Running' if self.base.runtime.timeline.is_playing() else 'Paused / armed') if s.running else 'Hold'
                row['readout'].text = f'{name.title()} offset: {s.angle:.2f} deg | {status}'
