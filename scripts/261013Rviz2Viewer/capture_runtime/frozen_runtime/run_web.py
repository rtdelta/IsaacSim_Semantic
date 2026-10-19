"""Run with system Python; stdlib backend works without any package download."""
import argparse
from pathlib import Path
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=17875)
    parser.add_argument('--output',default='/root/gpufree-data/semantic/output/sensor_visualizer/v06')
    parser.add_argument('--socket');parser.add_argument('--backend',choices=['stdlib','asgi'],default='stdlib')
    args=parser.parse_args();root=Path(__file__).resolve().parent
    from sensor_visualizer_v06.web_service import WebService,serve
    service=WebService(root,args.output,args.socket or Path(args.output)/'runtime/engine.sock')
    print(f'Sensor Visualizer v06: http://127.0.0.1:{args.port}',flush=True)
    if args.backend=='asgi':
        from sensor_visualizer_v06.web_asgi import build_app
        import uvicorn
        uvicorn.run(build_app(service),host='127.0.0.1',port=args.port)
    else:serve(service,port=args.port)
if __name__=='__main__':main()
