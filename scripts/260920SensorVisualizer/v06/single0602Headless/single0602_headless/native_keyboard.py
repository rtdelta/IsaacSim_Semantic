"""Viewport-only adapter; KEY_REPEAT cannot resurrect cleared keys."""
import time
from .keyboard_control import KEYS

def enum_name(value):
    return str(value if isinstance(value,str) else getattr(value,'name','')).strip().upper().rsplit('.',1)[-1]

class NativeKeyboard:
    def __init__(self, keyboard, context, notify, configure):
        self.keyboard, self.context, self.notify, self.configure = keyboard, context, notify, configure
        self.reason='waiting_for_viewport'; self.events=0; self.last_event=None; self.sequence=0; self.focus={}
    @property
    def keys(self): return self.keyboard.source_keys('native')
    def clear(self, reason):
        if self.keyboard.active_source=='native': self.keyboard.clear(reason,source='native')
        self.reason=reason
    def poll_focus(self):
        self.focus=dict(self.context())
        reason=next((name for name,passed in (
            ('window_unfocused',self.focus['application_focused']),
            ('viewport_unfocused',self.focus['viewport_focused']),
            ('input_blocked',not self.focus['input_blocked']),
            ('motion_paused',self.focus['playing']),
            ('keyboard_disabled',self.keyboard.enabled)) if not passed),None)
        if reason: self.clear(reason)
        return reason
    def handle(self,event):
        kind=enum_name(event.type)
        if kind not in ('KEY_PRESS','KEY_REPEAT','KEY_RELEASE'):return True
        key=enum_name(event.input)
        if key not in KEYS|{'F8'}: return True
        self.events+=1; self.last_event={'key':key,'kind':kind,'received_ns':time.monotonic_ns()}
        reason=self.poll_focus()
        if key=='F8':
            self.notify('native_key',**self.last_event,outcome='mode_shortcut',input_epoch=self.keyboard.input_epoch)
            if kind=='KEY_PRESS' and self.focus['application_focused'] and self.focus['viewport_focused'] and not self.focus['input_blocked']:
                self.configure({'enabled':not self.keyboard.enabled},source='native_f8')
            return False
        if reason:
            self.notify('native_key',**self.last_event,outcome=reason,input_epoch=self.keyboard.input_epoch)
            return True
        keys=self.keys
        if kind=='KEY_REPEAT':
            self.notify('native_key',**self.last_event,outcome='held_repeat' if key in keys else 'ignored_repeat',input_epoch=self.keyboard.input_epoch)
            return key not in keys
        if kind=='KEY_RELEASE':
            if key not in keys:return True
            keys.discard(key)
        else:keys.add(key)
        self.sequence+=1
        self.keyboard.update('native',keys,self.keyboard.input_epoch,self.sequence)
        self.reason='accepted'
        self.notify('native_key',**self.last_event,outcome='accepted',input_epoch=self.keyboard.input_epoch)
        return False
