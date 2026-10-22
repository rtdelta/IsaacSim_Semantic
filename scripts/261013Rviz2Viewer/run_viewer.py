"""Run using existing system ROS Jazzy, without Isaac or web dependencies."""
import argparse, datetime, json, os, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def resolve_capture(path):
    if path!='latest':return Path(path).resolve()
    latest=json.loads((ROOT/'reports/latest_capture.json').read_text())
    result=json.loads((Path(latest['directory'])/'capture/result.json').read_text())
    if not result.get('validation',{}).get('passed'):raise ValueError('Latest capture is not complete and validated')
    return Path(result['capture']['session'])

def find_assets(capture):
    for parent in (capture,*list(capture.parents)[:4]):
        if (parent/'viewer_assets/manifest.json').is_file():return parent/'viewer_assets'
    raise ValueError('Pass --assets with the exported Scene18 viewer_assets directory')

def main():
    p=argparse.ArgumentParser();p.add_argument('--capture',default='latest');p.add_argument('--assets');p.add_argument('--cache');p.add_argument('--port',type=int,default=8767);p.add_argument('--rviz',action='store_true');p.add_argument('--index-only',action='store_true');p.add_argument('--domain-id',type=int,default=43);p.add_argument('--play',action='store_true');p.add_argument('--exit-after-end',action='store_true');a=p.parse_args()
    from rviz_viewer.index import build_index
    capture=resolve_capture(a.capture);cache=Path(a.cache) if a.cache else capture/'viewer_cache/index.sqlite'
    index=build_index(capture,cache)
    print(json.dumps({'capture':str(capture),'groups':len(index.frames),'cache':str(cache),'audit':str(cache.with_suffix('.audit.json'))}),flush=True)
    if a.index_only:return 0
    import rclpy
    from rviz_viewer.player import Player
    from rviz_viewer.web import serve
    from make_rviz_config import write_config
    assets=Path(a.assets) if a.assets else find_assets(capture)
    logs=capture/'viewer_logs'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    rclpy.init(domain_id=a.domain_id);node=rclpy.create_node('rviz2_group_viewer')
    player=server=child=None
    try:
        player=Player(node,index,assets,logs);server=serve(player,a.port)
        config=logs/'viewer.rviz';write_config(config,player.state['topics'])
        if a.rviz:
            env=os.environ.copy();env['ROS_DOMAIN_ID']=str(a.domain_id)
            child=subprocess.Popen(['rviz2','-d',str(config),'--ros-args','-p','use_sim_time:=true'],env=env,stdout=(logs/'rviz.log').open('wb'),stderr=subprocess.STDOUT)
        print(f'Control page http://127.0.0.1:{a.port} ; logs {logs}',flush=True)
        if a.play:player.request({'action':'play'})
        while rclpy.ok():
            player.tick();rclpy.spin_once(node,timeout_sec=.005)
            if child and child.poll() is not None:raise RuntimeError('RViz exited; see '+str(logs/'rviz.log'))
            if a.exit_after_end and player.state['group']==len(index.frames)-1 and not player.state['playing']:break
    except KeyboardInterrupt:pass
    finally:
        if server:server.shutdown();server.server_close()
        if player:player.close()
        if child and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        node.destroy_node();rclpy.shutdown()
    return 0

if __name__=='__main__':raise SystemExit(main())
