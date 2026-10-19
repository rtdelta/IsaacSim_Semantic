"""Byte-bounded CPU-only evidence writer and independent file readback."""
import hashlib
import json
from pathlib import Path
import queue
import threading
import time


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def rows(path):
    path=Path(path)
    return [json.loads(line)['data'] for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


class EvidenceWriter:
    def __init__(self,directory,queue_bytes,disk_bytes,compress_gmo=False):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.limit=queue_bytes;self.disk_limit=disk_bytes
        self.queue=queue.Queue(4096);self.lock=threading.Lock()
        self.inflight=self.peak=self.reserved_disk=self.written=0
        self.error=None;self.closed=False;self.streams={}
        self.compress_gmo=compress_gmo
        self.thread=threading.Thread(target=self._run,name='paired-owned-evidence',daemon=True);self.thread.start()
    def submit(self,kind,path,value,nbytes):
        with self.lock:
            if self.closed or self.error:raise RuntimeError(self.error or 'Evidence writer closed')
            if self.inflight+nbytes>self.limit:raise RuntimeError('evidence_queue_budget: stop without dropping payloads')
            if self.reserved_disk+nbytes>self.disk_limit:raise RuntimeError('evidence_disk_budget')
            self.inflight+=nbytes;self.reserved_disk+=nbytes;self.peak=max(self.peak,self.inflight)
            try:self.queue.put_nowait((kind,path,value,nbytes))
            except queue.Full:raise RuntimeError('evidence_queue_item_budget')
    def event(self,path,value):
        raw=(json.dumps({'data':value},ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
        self.submit('jsonl',path,raw,len(raw))
    def payload(self,path,array,png=False):
        # Caller hands over an independently owned CPU array; no SDK calls here.
        array.flags.writeable=False
        compress=self.compress_gmo and path.startswith('trace_samples/gmo_') and not path.startswith('trace_samples/gmo_prefix_') and path.endswith('.bin')
        if compress:path+='.gz'
        self.submit('gzip_array' if compress else ('png' if png else 'array'),path,array,int(array.nbytes)+4096)
        return path
    def _run(self):
        try:
            while True:
                item=self.queue.get()
                if item is None:break
                kind,name,value,nbytes=item;path=self.directory/name;path.parent.mkdir(parents=True,exist_ok=True)
                if kind=='jsonl':
                    if name not in self.streams:self.streams[name]=path.open('xb')
                    self.streams[name].write(value);self.streams[name].flush();self.written+=len(value)
                elif kind=='png':
                    from PIL import Image
                    Image.fromarray(value).save(path,format='PNG',compress_level=1)
                    self.written+=path.stat().st_size
                elif kind=='gzip_array':
                    import gzip
                    with path.open('xb') as file:
                        with gzip.GzipFile(filename='',mode='wb',fileobj=file,compresslevel=1,mtime=0) as stream:
                            stream.write(memoryview(value).cast('B'))
                    self.written+=path.stat().st_size
                else:
                    with path.open('xb') as stream:value.tofile(stream)
                    self.written+=path.stat().st_size
                with self.lock:self.inflight-=nbytes
        except Exception as exc:self.error=str(exc)
        finally:
            for stream in self.streams.values():stream.close()
    def close(self):
        self.closed=True;self.queue.put(None,timeout=5);self.thread.join(60)
        if self.thread.is_alive():raise RuntimeError('Evidence drain timeout')
        if self.error:raise RuntimeError('Evidence save failed: '+self.error)
        files=[]
        for path in sorted(self.directory.rglob('*')):
            if path.is_file() and path.name!='file_manifest.json':
                files.append({'path':path.relative_to(self.directory).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)})
        save(self.directory/'file_manifest.json',{'schema_version':1,'files':files,'queue_peak_bytes':self.peak,
            'reserved_disk_bytes':self.reserved_disk,'written_bytes':self.written,'readback_scope':'all evidence files reopened and SHA256 hashed'})


def verify(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'file_manifest.json').read_text())
    for item in manifest['files']:
        path=directory/item['path']
        if path.stat().st_size!=item['bytes'] or digest(path)!=item['sha256']:raise ValueError('Evidence identity mismatch: '+str(path))
    return len(manifest['files'])
