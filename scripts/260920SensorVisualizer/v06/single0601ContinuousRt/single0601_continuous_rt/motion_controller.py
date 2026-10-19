"""All input commands enter a bounded queue and integrate once per physical step."""
from collections import deque
import math
import time
from .common import ContractError

KEYS=set('WSADR FQEIKJLUOTGYH'.replace(' ',''))


class MotionController:
    def __init__(self,motion,notify=lambda e:None,capacity=64):
        self.motion,self.notify,self.capacity=motion,notify,capacity
        self.queue=deque()
        self.keys=set()
        self.revision=0
        self.last_step=None
        self.trajectory=None
        self.running=True

    def enqueue(self,source,action,values=None):
        if len(self.queue)>=self.capacity:
            raise ContractError('control_queue_full','Control queue capacity exhausted')
        if source not in ('native_keyboard','parameters','trajectory','acceptance','lifecycle'):
            raise ContractError('control_source','Unknown command source')
        self.revision+=1
        event={'command_revision':self.revision,'source':source,'action':action,'values':values or {},'received_monotonic_ns':str(time.monotonic_ns())}
        self.queue.append(event)
        return self.revision

    def clear_keys(self,reason):
        if self.keys or any(e['action']=='keys' and e['values'].get('pressed') for e in self.queue):
            self.keys.clear()
            self.enqueue('native_keyboard','keys',{'pressed':[],'reason':reason})

    def step(self,dt,physical_step,simulation_time):
        if self.last_step==physical_step:
            raise ContractError('double_integration','A physical step can be integrated only once')
        self.last_step=physical_step
        m=self.motion
        applied=None
        while self.queue:
            event=self.queue.popleft()
            v,action=event['values'],event['action']
            if action=='base_velocity':
                m.command_base('velocity',speed=float(v['speed_m_s']),yaw_rate_deg=float(v['yaw_rate_deg_s']))
            elif action=='base_pose':
                m.command_base('direct',x=float(v['x_m']),y=float(v['y_m']),yaw_deg=float(v['yaw_deg']))
            elif action=='joint':
                m.command('execute',commands=v['commands'])
            elif action=='hold':
                m.command('hold')
                m.command_base('hold')
                self.keys.clear()
                self.trajectory=None
            elif action=='keys':
                pressed=set(v['pressed'])
                if not pressed<=KEYS:
                    raise ContractError('keyboard_key','Unsupported motion key')
                self.keys=pressed
                m.base_controller.hold()
                self.trajectory=None
            elif action=='trajectory':
                points=v['waypoints']
                if len(points)<2 or any(len(p)!=4 or not all(math.isfinite(float(x)) for x in p) for p in points) or any(a[0]>=b[0] for a,b in zip(points,points[1:])):
                    raise ContractError('trajectory','Waypoints are increasing [simulation_s,x_m,y_m,yaw_deg]')
                self.trajectory={'origin':simulation_time,'points':points}
                self.keys.clear()
            else:
                raise ContractError('control_action','Unsupported command: '+action)
            applied=event['command_revision']
            self.notify(dict(event,applied_physical_step=physical_step,applied_simulation_time_ns=str(round(simulation_time*1e9)),
                             applied_monotonic_ns=str(time.monotonic_ns())))
        if self.trajectory:
            elapsed=simulation_time-self.trajectory['origin']
            points=self.trajectory['points']
            a,b=points[0],points[1]
            for a,b in zip(points,points[1:]):
                if elapsed<=b[0]:
                    break
            t=min(1.,max(0.,(elapsed-a[0])/(b[0]-a[0])))
            m.base_controller.direct(*(a[i]+t*(b[i]-a[i]) for i in range(1,4)))
        if self.keys:
            c=m.base_controller
            def direction(a,b):return int(a in self.keys)-int(b in self.keys)
            forward,side=direction('W','S'),direction('A','D')
            d=.5*dt/max(1.,math.hypot(forward,side))
            c.x+=d*(forward*math.cos(c.heading)-side*math.sin(c.heading))
            c.y+=d*(forward*math.sin(c.heading)+side*math.cos(c.heading))
            c.z+=.5*dt*direction('R','F')
            c.heading+=math.radians(10*dt*direction('Q','E'))
            for name,pair in {'pitch':('I','K'),'roll':('J','L')}.items():
                state=c.tilt.states[name]
                change=direction(*pair)
                if change:
                    state.running=False
                    state.angle=min(state.maximum,max(state.minimum,state.angle+10*dt*change))
            for role,pair in {'boom':('U','O'),'arm':('T','G'),'bucket':('Y','H')}.items():
                for joint in m.config['joints']:
                    if joint['role']==role:
                        state=m.controller.states[joint['name']]
                        change=direction(*pair)
                        if change:
                            state.running=False
                            state.angle=min(state.maximum,max(state.minimum,state.angle+10*dt*change))
        m.controller.step(dt)
        m.base_controller.step(dt)
        m._apply_controlled_base(m._command_angles())
        return applied


class NativeKeyboard:
    def __init__(self,controller,can_control=lambda:True):
        import carb.input
        import omni.appwindow
        import omni.kit.app
        self.controller,self.can_control=controller,can_control
        self.window=omni.appwindow.get_default_app_window()
        self.interface=carb.input.acquire_input_interface()
        self.device=self.window.get_keyboard() if self.window else None
        self.pressed=set()
        self.keyboard_subscription=self.interface.subscribe_to_keyboard_events(self.device,self.event) if self.device else None
        self.update_subscription=omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(lambda e:self.check_focus())

    def eligible(self):
        import carb.input
        import omni.ui as ui
        import omni.kit.viewport.utility
        viewport=omni.kit.viewport.utility.get_active_viewport_window()
        # Require the viewport itself; focus on a text field or another panel clears input.
        focused=bool(viewport and getattr(viewport,'focused',False))
        return bool(self.window and self.window.is_focused() and focused and not self.window.get_input_blocking_state(carb.input.DeviceType.KEYBOARD) and self.can_control())

    def clear(self,reason):
        if self.pressed or self.controller.keys:
            self.pressed.clear()
            self.controller.clear_keys(reason)

    def check_focus(self):
        if not self.eligible():
            self.clear('viewport_focus_or_control_lost')

    def event(self,event):
        kind=getattr(event.type,'name','').upper()
        key=getattr(event.input,'name','').upper()
        if key not in KEYS or kind not in ('KEY_PRESS','KEY_REPEAT','KEY_RELEASE'):
            return True
        if kind=='KEY_RELEASE':
            if key in self.pressed:
                self.pressed.remove(key)
                self.controller.enqueue('native_keyboard','keys',{'pressed':sorted(self.pressed)})
            return False
        if not self.eligible():
            self.clear('input_blocked')
            return True
        if key not in self.pressed:
            self.pressed.add(key)
            self.controller.enqueue('native_keyboard','keys',{'pressed':sorted(self.pressed)})
        return False

    def close(self):
        self.clear('closed')
        if self.keyboard_subscription is not None:
            self.interface.unsubscribe_to_keyboard_events(self.device,self.keyboard_subscription)
        self.update_subscription=None
