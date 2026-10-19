"""Native event adapter; character input never becomes a motion command."""
import time

from .keyboard_control import KEYS

def enum_name(value):
    name=value if isinstance(value,str) else getattr(value,'name','')
    return str(name).strip().upper().rsplit('.',1)[-1]

class NativeKeyboard:
    def __init__(self,keyboard,context,notify):
        self.keyboard,self.context,self.notify=keyboard,context,notify
        self.keys=set();self.reason='waiting';self.events=0;self.last_event=None
    def clear(self,reason):
        self.keys.clear();self.keyboard.sources.pop('native',None);self.reason=reason
    def handle(self,event):
        kind=enum_name(event.type)
        if kind not in ('KEY_PRESS','KEY_REPEAT','KEY_RELEASE'):return True
        key=enum_name(event.input)
        if key not in KEYS and key!='F8':return True
        stamp=time.monotonic_ns();self.events+=1
        self.last_event={'key':key,'kind':kind,'received_ns':stamp}
        focused,blocked,playing=self.context()
        if kind=='KEY_RELEASE' and key in self.keys:
            self.keys.discard(key);self.keyboard.update('native',self.keys)
            self.notify('native_key',key=key,kind=kind,received_ns=stamp,outcome='released');return False
        if not focused or blocked:
            self.clear('input_blocked' if blocked else 'window_unfocused')
            self.notify('native_key',key=key,kind=kind,received_ns=stamp,outcome=self.reason);return True
        if key=='F8':
            if kind=='KEY_PRESS':
                self.keyboard.enabled=not self.keyboard.enabled;self.keyboard.clear();self.clear('mode_changed')
                self.notify('keyboard_mode_changed',enabled=self.keyboard.enabled,source='native')
            return False
        if not self.keyboard.enabled or not playing:
            self.clear('keyboard_disabled' if not self.keyboard.enabled else 'motion_paused')
            self.notify('native_key',key=key,kind=kind,received_ns=stamp,outcome=self.reason);return True
        self.reason='accepted'
        if kind in ('KEY_PRESS','KEY_REPEAT'):
            if key not in self.keys:
                self.keys.add(key);self.keyboard.update('native',self.keys)
                self.notify('native_key',key=key,kind=kind,received_ns=stamp,outcome='accepted')
        return False
