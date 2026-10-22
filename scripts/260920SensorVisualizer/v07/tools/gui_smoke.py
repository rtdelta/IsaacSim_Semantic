"""Owned GUI + real HTTP smoke; preserves quality and does not touch old versions."""
import json
import os
import threading
import time
import urllib.request
import uuid
from native_validation import Validation,ROOT
from sensor_visualizer_v07.control_ipc import request
from sensor_visualizer_v07.web_service import WebService,make_server

class GUIValidation(Validation):
    def v07(self):
        self.status('gui_owner_start');start=time.monotonic()
        state,directory=self.start_owner('v07');self.report['gui_owner_ready_s']=time.monotonic()-start
        service=WebService(ROOT,directory,self.socket);server=make_server(service,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base='http://127.0.0.1:'+str(server.server_address[1])
        def http(path,value=None):
            if value is None:return json.load(opener.open(base+path,timeout=5))
            req=urllib.request.Request(base+path,data=json.dumps(value).encode(),
                headers={'Content-Type':'application/json','X-SV07-Token':service.token})
            return json.load(opener.open(req,timeout=5))
        def applied(action,payload=None):
            command={'action':action,'payload':payload or {},'command_id':uuid.uuid4().hex}
            accepted=http('/api/command',command)
            def receipt():
                row=next((r for r in request(self.socket,{'action':'status'})['receipts'] if r['command_id']==accepted['command_id']),None)
                if row and row['state']!='applied':raise RuntimeError(str(row))
                return row
            return self.until(receipt,30)
        try:
            self.status('gui_http_controls')
            html=opener.open(base,timeout=5).read().decode()
            assert all(label in html for label in ('Play Simulation','Start Recording','Apply Mount','Prepare Capture Service'))
            assert http('/api/status')['transport']=='stdlib_http_polling'
            applied('pause');applied('hold')
            for mode in ('direct','target','periodic'):
                applied('motion',{'joints':{'boom':{'mode':mode,'target':5,'speed':10,'lower':-10,'upper':10}}})
                current=request(self.socket,{'action':'status'})
                assert any(control['mode']==mode for control in current['joint_controls'].values())
            applied('hold');applied('motion',{'tilt':{'pitch':{'mode':'direct','target':2},'roll':{'mode':'direct','target':-2}}})
            current=request(self.socket,{'action':'status'})
            assert abs(current['tilt_controls']['pitch']['angle']-2)<1e-5
            mount=next(m for m in current['state']['mounts'] if m['editable'])
            position=list(mount['position_m']);position[0]+=.01
            applied('mount',{'id':mount['id'],'position_m':position,'rotation_deg':mount['rotation_deg']})
            current=request(self.socket,{'action':'status'})
            actual=next(m for m in current['state']['mounts'] if m['id']==mount['id'])
            assert abs(actual['position_m'][0]-position[0])<1e-6
            applied('reset_mounts');applied('stop');applied('play')
            applied('keyboard',{'enabled':True,'joint_speed':100})
            before=request(self.socket,{'action':'status'})['state']['position_world_m']
            time.sleep(4)
            after=request(self.socket,{'action':'status'})['state']['position_world_m']
            assert any(abs(a-b)>1e-5 for a,b in zip(after,before)),'Continuous keyboard input did not move base'
            state=request(self.socket,{'action':'status'});trajectory=self.trajectory(state,directory,8)
            self.report['gui_controls_verified']=['HTTP panel','joint modes','pitch/roll','mount','stop/play','keyboard base motion']
            self.status('gui_service_prepare');start=time.monotonic();http('/api/service',{'action':'prepare'})
            self.until(lambda:service.supervisor.worker_status().get('phase')=='idle',600)
            self.report['gui_worker_prepare_s']=time.monotonic()-start
            sizes=(2,2) if os.environ.get('SV07_GUI_SHORT')=='1' else (8,3)
            for name,groups in zip(('gui_first','gui_repeat'),sizes):
                self.status(name);start=time.monotonic()
                task=http('/api/capture',{'mode':'offline','trajectory':str(trajectory),'groups':groups,'ros_preview':False})
                result=self.wait_task(service.supervisor,task['task_id'])
                self.report['results'].append({'case':name,'total_wall_s':time.monotonic()-start,**result})
            self.status('gui_restore_and_reinitialize')
            applied('stop');applied('play');applied('exit');applied('reinitialize');applied('play')
            http('/api/service',{'action':'close'})
            self.until(lambda:service.supervisor.worker_status().get('phase')=='not_running',60)
        finally:
            for row in service.supervisor.status():
                if row['running']:
                    service.supervisor.control(row['task_id'],'stop');self.wait_task(service.supervisor,row['task_id'])
            if service.supervisor.worker_status().get('phase')=='idle':service.supervisor.close_worker()
            service.close();server.shutdown();server.server_close();thread.join(timeout=2)
            self.stop_owner()

if __name__=='__main__':
    os.environ.update(SV07_SKIP_BASELINE='1',SV07_VALIDATION_GUI='1')
    GUIValidation().run()
