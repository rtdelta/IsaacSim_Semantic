"""Optional FastAPI/WebSocket adapter, never imported by the stdlib backend."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from urllib.parse import urlparse
from fastapi import FastAPI,Request,WebSocket,HTTPException
from fastapi.responses import HTMLResponse,FileResponse,Response

def build_app(service):
    @asynccontextmanager
    async def lifespan(app):
        yield
        service.closed=True
    app=FastAPI(lifespan=lifespan)
    def authorize(request):
        if not secrets.compare_digest(request.headers.get('x-s0602-token',''),service.token):raise HTTPException(403,'Missing control token')
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc!=request.headers.get('host'):raise HTTPException(403,'Cross-origin control')
    @app.get('/')
    async def index():return HTMLResponse((service.project/'web/static/index.html').read_text(encoding='utf-8').replace('__CONTROL_TOKEN__',service.token))
    @app.get('/app.js')
    async def script():return FileResponse(service.project/'web/static/app.js')
    @app.get('/style.css')
    async def style():return FileResponse(service.project/'web/static/style.css')
    @app.get('/api/status')
    async def status():
        s=await asyncio.to_thread(service.status);s['transport']='asgi_websocket';return s
    @app.get('/api/export')
    async def export(path:str):return Response(await asyncio.to_thread(service.export,path),media_type='application/zip')
    @app.get('/api/capture_plan')
    async def capture_plan(request:Request):
        try:
            payload=dict(request.query_params)
            if 'groups' in payload:payload['groups']=int(payload['groups'])
            return await asyncio.to_thread(service.supervisor.preview,payload)
        except (ValueError,KeyError,OSError) as exc:raise HTTPException(400,str(exc))
    @app.post('/api/{action}')
    async def command(action:str,request:Request):
        authorize(request)
        if int(request.headers.get('content-length',0))>64*1024**2:raise HTTPException(413,'Import too large')
        try:
            if action=='import_zip':return await asyncio.to_thread(service.import_zip,await request.body())
            m=await request.json()
            if action=='command':return await asyncio.to_thread(service.command,m)
            if action=='capture':return await asyncio.to_thread(service.supervisor.start,m)
            if action=='task':return await asyncio.to_thread(service.supervisor.control,m['task_id'],m['action'])
            if action=='import':return await asyncio.to_thread(service.import_trajectory,m)
            raise HTTPException(404,'Unknown action')
        except (ValueError,KeyError,OSError) as exc:raise HTTPException(400,str(exc))
    @app.websocket('/ws')
    async def socket(ws:WebSocket):
        if urlparse(ws.headers.get('origin','')).netloc!=ws.headers.get('host'):await ws.close(code=1008);return
        await ws.accept()
        try:
            auth=await asyncio.wait_for(ws.receive_json(),5)
            if auth.get('type')!='authenticate' or not secrets.compare_digest(str(auth.get('credential','')),service.token):
                await ws.close(code=1008);return
        except (TimeoutError,ValueError):await ws.close(code=1008);return
        send_lock=asyncio.Lock()
        async def send(value):
            async with send_lock:await ws.send_json(value)
        async def publish():
            while True:
                state=await asyncio.to_thread(service.status);state['transport']='asgi_websocket'
                await send({'type':'status','data':state});await asyncio.sleep(.1)
        task=asyncio.create_task(publish())
        try:
            while True:
                command=await ws.receive_json();result=await asyncio.to_thread(service.command,command)
                await send({'type':'receipt','data':result})
        finally:task.cancel();await asyncio.gather(task,return_exceptions=True)
    return app
