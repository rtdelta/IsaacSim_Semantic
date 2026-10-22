"""Exercise real ROS CDR, group seeks, reverse clock and HTTP on the instance."""
import argparse, json, sys, tempfile, time, urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import rclpy
from rviz_viewer.index import build_index
from rviz_viewer.player import Player
from rviz_viewer.web import serve

def main(capture,assets,report,cache=None,logs=None):
    index=build_index(capture,Path(cache) if cache else Path(capture)/'viewer_cache/index.sqlite')
    rclpy.init(domain_id=54);node=rclpy.create_node('viewer_integration_test')
    directory=(Path(logs) if logs else Path(capture)/'viewer_logs')/('integration_'+str(time.time_ns()))
    player=Player(node,index,assets,directory);web=serve(player,8768)
    results=[]
    def run(command,group):
        player.request(command);player.tick()
        for _ in range(30):rclpy.spin_once(node,timeout_sec=.01)
        assert player.state['group']==group and player.state['error'] is None,player.state
        results.append({'command':command,'result_group':group})
    try:
        run({'action':'seek','group':1},1)
        run({'action':'step','delta':-1},0)
        run({'action':'seek','group':2},2)
        run({'action':'seek','group':1},1)
        run({'action':'configure','model_offset':1},1)
        run({'action':'configure','model_offset':-1},1)
        run({'action':'configure','model_offset':0,'mode':'original'},1)
        run({'action':'seek','group':0},0)
        run({'action':'step','delta':1},1)
        run({'action':'configure','mode':'synchronized'},1)
        status=json.load(urllib.request.urlopen('http://127.0.0.1:8768/api/status'))
        request=urllib.request.Request('http://127.0.0.1:8768/api/control',data=json.dumps({'action':'seek','group':2}).encode(),headers={'Content-Type':'application/json'})
        assert urllib.request.urlopen(request).status==202
        player.tick();assert player.state['group']==2
        for _ in range(30):rclpy.spin_once(node,timeout_sec=.01)
        events=[json.loads(x) for x in (directory/'playback_events.jsonl').read_text().splitlines()]
        published={(x['topic'],x['header_stamp_ns'],x['payload_sha256']) for x in events if x['event']=='published' and 'payload_sha256' in x}
        received={(x['topic'],x['stamp_ns'],x['payload_sha256']) for x in events if x['event']=='received' and x['points']>0}
        assert received and received<=published,'Received point bytes do not match source publication'
        assert len({x[0] for x in received})==13
        value={'passed':True,'source_groups':len(index.frames),'tested_commands':results,'http_status':status,'received_unique_cloud_payloads':len(received),'received_topics':13,'received_hashes_match_published':True,'event_log':str(directory/'playback_events.jsonl')}
        Path(report).write_text(json.dumps(value,indent=2));print(json.dumps(value))
    finally:
        web.shutdown();web.server_close();player.close();node.destroy_node();rclpy.shutdown()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture');p.add_argument('assets');p.add_argument('report');p.add_argument('--cache');p.add_argument('--logs');a=p.parse_args();main(a.capture,a.assets,a.report,a.cache,a.logs)
