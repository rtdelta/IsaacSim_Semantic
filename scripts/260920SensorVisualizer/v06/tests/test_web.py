import io,json,threading,tempfile,unittest,urllib.request,urllib.error,zipfile
from pathlib import Path
from unittest.mock import patch
from sensor_visualizer_v06.web_service import WebService,make_server
from test_interaction_trajectory import state

class WebTests(unittest.TestCase):
    def test_http_static_status_token_and_import(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            service=WebService(root,temp,Path(temp)/'absent.sock')
            server=make_server(service,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_address[1])
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                html=opener.open(url).read().decode();self.assertIn(service.token,html);self.assertIn('Start Recording',html)
                result=json.load(opener.open(url+'/api/status'));self.assertEqual(result['transport'],'stdlib_http_polling')
                payload=json.dumps({'states':[state(0),state(1,1)],'metadata':{'scene':'/scene.usda','joint_names':['boom_joint']}}).encode()
                bad=urllib.request.Request(url+'/api/import',data=payload,headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as context:opener.open(bad)
                self.assertEqual(context.exception.code,403)
                req=urllib.request.Request(url+'/api/import',data=payload,headers={'Content-Type':'application/json','X-SV06-Token':service.token})
                imported=json.load(opener.open(req));self.assertEqual(imported['rows'],2)
            finally:service.closed=True;server.shutdown();server.server_close();thread.join(timeout=2)
    def test_zip_import_export_and_path_boundary(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            service=WebService(root,temp,Path(temp)/'absent.sock')
            try:
                p=service.import_trajectory({'states':[state(0),state(1,1)],'metadata':{'joint_names':['boom_joint']}})['path']
                # Imported trajectories are JSONL; generate their editable CSV for export.
                from sensor_visualizer_v06.trajectory import TrajectoryRecorder
                q=Path(temp)/'recorded';rec=TrajectoryRecorder(q,{'joint_names':['boom_joint']});rec.append(state(0));rec.append(state(1,1));rec.close()
                data=service.export(q);value=service.import_zip(data);self.assertEqual(value['rows'],2)
                with self.assertRaises(ValueError):service.export(Path(temp).parent)
            finally:service.closed=True
if __name__=='__main__':unittest.main()
