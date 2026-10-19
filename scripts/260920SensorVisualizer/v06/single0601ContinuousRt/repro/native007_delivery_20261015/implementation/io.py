"""Independent bounded CPU evidence sink. No simulator or project imports."""
import gzip,hashlib,json,queue,threading
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')

def rows(path):
    p=Path(path)
    return [json.loads(s)['data'] for s in p.read_text(encoding='utf-8').splitlines()] if p.exists() else []

class Sink:
    def __init__(self,path,queue_bytes=268435456,disk_bytes=2147483648):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.queue=queue.Queue(4096);self.lock=threading.Lock();self.limit=queue_bytes;self.disk_limit=disk_bytes
        self.inflight=self.peak=self.reserved=self.written=0;self.error=None;self.closed=False
        self.thread=threading.Thread(target=self.work,daemon=True,name='independent-native-save');self.thread.start()
    def submit(self,name,data,compressed=False):
        with self.lock:
            if self.closed or self.error:raise RuntimeError(self.error or 'sink closed')
            cost=len(data)+(0 if name.endswith('.jsonl') else 4096)
            if self.inflight+cost>self.limit or self.reserved+cost>self.disk_limit:raise RuntimeError('evidence budget exceeded; no wait/drop')
            self.queue.put_nowait((name,data,compressed,cost));self.inflight+=cost;self.reserved+=cost;self.peak=max(self.peak,self.inflight)
        return name
    def event(self,name,data):return self.submit(name,(json.dumps({'data':data},allow_nan=False)+'\n').encode())
    def work(self):
        streams={}
        try:
            while True:
                item=self.queue.get()
                if item is None:break
                name,data,compressed,cost=item;p=self.path/name;p.parent.mkdir(parents=True,exist_ok=True)
                if name.endswith('.jsonl'):
                    if name not in streams:streams[name]=p.open('xb')
                    streams[name].write(data);streams[name].flush();self.written+=len(data)
                else:
                    with p.open('xb') as f:
                        if compressed:
                            with gzip.GzipFile(filename='',mode='wb',fileobj=f,compresslevel=1,mtime=0) as z:z.write(data)
                        else:f.write(data)
                    self.written+=p.stat().st_size
                with self.lock:self.inflight-=cost
        except Exception as exc:self.error=str(exc)
        finally:
            for f in streams.values():f.close()
    def close(self):
        self.closed=True
        self.queue.put(None,timeout=5);self.thread.join(60)
        if self.thread.is_alive() or self.error:raise RuntimeError(self.error or 'bounded save timeout')
        files=[{'path':p.relative_to(self.path).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(self.path.rglob('*')) if p.is_file() and p.name!='file_manifest.json']
        save(self.path/'file_manifest.json',{'files':files,'queue_peak_bytes':self.peak,'reserved_disk_bytes':self.reserved,'written_bytes':self.written})

def verify(path):
    path=Path(path);d=json.loads((path/'file_manifest.json').read_text())
    for x in d['files']:
        p=path/x['path']
        if p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:raise ValueError('Evidence SHA/length mismatch: '+str(p))
    return len(d['files'])
