"""Installed Carb provider -> real Kit subscriber -> actual Articulation state.

This is SDK event injection, not proof of a human's remote desktop latency.
"""
import asyncio,json,math,time

async def run(runtime):
    import carb.input
    keyboard=runtime.keyboard_device;provider=runtime.input.get_input_provider()
    if not runtime.window.is_focused():raise RuntimeError('Native test window is unfocused; human focus verification needed')
    if runtime.window.get_input_blocking_state(carb.input.DeviceType.KEYBOARD):raise RuntimeError('Native test input is blocked by UI focus')
    runtime.command({'action':'stop'});runtime.command({'action':'play'})
    checks=[]
    async def pulse(name,duration=.5):
        before=runtime._read_state();key=getattr(carb.input.KeyboardInput,name)
        provider.buffer_keyboard_key_event(keyboard,carb.input.KeyboardEventType.KEY_PRESS,key,0)
        # CHAR input exercises the exact variant that previously raised .name.
        provider.buffer_keyboard_char_event(keyboard,name.lower(),0)
        await asyncio.sleep(duration)
        provider.buffer_keyboard_key_event(keyboard,carb.input.KeyboardEventType.KEY_RELEASE,key,0)
        await asyncio.sleep(.15)
        return before,runtime._read_state()
    for key in ('W','S','A','D','R','F'):
        a,b=await pulse(key);delta=math.sqrt(sum((v-u)**2 for u,v in zip(a['position_world_m'],b['position_world_m'])))
        assert delta>.005,(key,delta,runtime.native.reason);checks.append({'key':key,'translation_m':delta})
    for key in ('Q','I','J'):
        a,b=await pulse(key);delta=max(abs(u-v) for u,v in zip(a['quaternion_xyzw'],b['quaternion_xyzw']))
        assert delta>.001,(key,delta,runtime.native.reason);checks.append({'key':key,'quaternion_delta':delta})
    names={j['role']:j['name'] for j in runtime.scene.motion.config['joints']}
    for key,role in (('U','boom'),('T','arm'),('Y','bucket')):
        joint=names[role]
        a,b=await pulse(key);delta=b['joints_deg'][joint]-a['joints_deg'][joint]
        assert delta>.2,(key,delta,runtime.native.reason);checks.append({'key':key,'joint_deg':delta})
    await pulse('F8',.05);assert not runtime.keyboard.enabled
    a,b=await pulse('W');assert a['position_world_m']==b['position_world_m']
    await pulse('F8',.05);assert runtime.keyboard.enabled
    runtime.command({'action':'pause'});a,b=await pulse('W');assert a['position_world_m']==b['position_world_m']
    for _ in range(5):runtime.command({'action':'stop'});runtime.command({'action':'play'});await asyncio.sleep(.1)
    runtime.command({'action':'pause'});assert not runtime.last_input_error
    report={'passed':True,'test':'installed_sdk_native_event_subscription','checks':checks,'f8_pause_stop_repeat':True,
        'native_events':runtime.native.events,'input_error':runtime.last_input_error,'last_input_apply_ms':runtime.keyboard.last_apply_ms,
        'human_remote_desktop_latency_verified':False}
    path=runtime.project/'reports/native_owner/native_keyboard_fix.json';path.write_text(json.dumps(report,indent=2));print('[SV06 NATIVE EVENT TEST] '+json.dumps(report),flush=True)
