"""Loopback-only, dependency-free playback control page."""
import json, threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

def serve(player,port):
    html=(Path(__file__).parent.parent/'web/index.html').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,data,kind):
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.path=='/':self.reply(200,html,'text/html; charset=utf-8')
            elif self.path=='/api/status':self.reply(200,json.dumps(player.snapshot()).encode(),'application/json')
            else:self.reply(404,b'Not found','text/plain')
        def do_POST(self):
            try:
                if self.path!='/api/control':raise ValueError('Unknown route')
                origin=self.headers.get('Origin')
                if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):raise ValueError('Cross-origin control refused')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<4096:raise ValueError('Invalid command size')
                player.request(json.loads(self.rfile.read(length)))
                self.reply(202,b'{"queued":true}','application/json')
            except Exception as exc:self.reply(400,json.dumps({'error':str(exc)}).encode(),'application/json')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,name='viewer-web',daemon=True);thread.start();return server
