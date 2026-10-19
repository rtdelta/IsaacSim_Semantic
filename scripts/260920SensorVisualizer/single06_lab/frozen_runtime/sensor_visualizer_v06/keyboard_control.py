"""Pressed-state integration; transferable to engine updates without repeat events."""
import math
import time

KEYS={'W','S','A','D','R','F','Q','E','I','K','J','L','U','O','T','G','Y','H'}
PAIRS={'boom':('U','O'),'arm':('T','G'),'bucket':('Y','H')}

class KeyboardControl:
    def __init__(self):
        self.sources={}; self.enabled=True; self.linear_speed=.5; self.angular_speed=10.; self.joint_speed=10.
        self.received_ns=0;self.input_revision=0;self.applied_revision=0;self.last_apply_ms=None
    def update(self,source,keys):
        if len(keys)>len(KEYS) or any(k not in KEYS for k in keys): raise ValueError('Unsupported key')
        self.sources[source]=(set(keys),time.monotonic())
        self.received_ns=time.monotonic_ns();self.input_revision+=1
    def clear(self): self.sources.clear()
    def pressed(self):
        now=time.monotonic(); keys=set()
        for source,(state,stamp) in list(self.sources.items()):
            if source!='native' and now-stamp>.5: self.sources.pop(source,None)
            else: keys.update(state)
        return keys if self.enabled else set()
    def step(self,motion,dt):
        keys=self.pressed()
        if not keys or dt<=0:return False
        c=motion.base_controller
        def v(pos,neg):return int(pos in keys)-int(neg in keys)
        # +local Y is left in this Z-up, +X-forward frame.
        forward=v('W','S'); side=v('A','D'); norm=max(1,math.hypot(forward,side))
        c.speed=c.yaw_rate=0
        d=self.linear_speed*dt/norm
        c.x+=d*(forward*math.cos(c.heading)-side*math.sin(c.heading))
        c.y+=d*(forward*math.sin(c.heading)+side*math.cos(c.heading))
        c.z+=self.linear_speed*dt*v('R','F'); c.heading+=math.radians(self.angular_speed*dt*v('Q','E'))
        for name,pair in {'pitch':('I','K'),'roll':('J','L')}.items():
            state=c.tilt.states[name]; change=v(*pair)
            if change: state.running=False; state.angle=max(state.minimum,min(state.maximum,state.angle+self.angular_speed*dt*change))
        for joint in motion.config['joints']:
            pair=PAIRS.get(joint['role'])
            if pair:
                change=v(*pair); state=motion.controller.states[joint['name']]
                if change:state.running=False;state.angle=max(state.minimum,min(state.maximum,state.angle+self.joint_speed*dt*change))
        return True
