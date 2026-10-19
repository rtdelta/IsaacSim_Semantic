"""Incident evidence collection. Execute on stdin, never import suspicious code.

Only reads remote files. The existing compromised loader remains active.
No process control, installations, configuration writes, or network probes.
"""
import base64, ctypes, datetime, gzip, hashlib, json, os, re, stat, struct, zlib

libc = ctypes.CDLL('libc.so.6', use_errno=True)
libc.syscall.restype = ctypes.c_long

def rawread(path, limit=16000000, tail=False):
    fd = os.open(path, os.O_RDONLY)
    try:
        if tail:
            s = os.fstat(fd)
            if stat.S_ISREG(s.st_mode) and s.st_size > limit:
                os.lseek(fd, s.st_size-limit, os.SEEK_SET)
        out = bytearray()
        buf = ctypes.create_string_buffer(65536)
        while len(out)<limit:
            n=libc.syscall(0,fd,buf,min(len(buf),limit-len(out)))
            if n<0: raise OSError(ctypes.get_errno(),'raw read')
            if not n: break
            out.extend(buf.raw[:n])
        return bytes(out)
    finally: os.close(fd)

def names(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        result=[]; buf=ctypes.create_string_buffer(65536)
        while True:
            n=libc.syscall(217,fd,buf,len(buf))
            if n<0: raise OSError(ctypes.get_errno(),'getdents64')
            if not n: break
            b=buf.raw[:n]; offset=0
            while offset<n:
                length=struct.unpack_from('H',b,offset+16)[0]
                if length<19: raise ValueError('directory record')
                name=b[offset+19:offset+length].split(b'\0',1)[0].decode(errors='replace')
                if name not in ('.','..'): result.append(name)
                offset+=length
        return sorted(result)
    finally: os.close(fd)

def meta(p):
    try:
        s=os.lstat(p)
        return dict(size=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,
                    mode=oct(stat.S_IMODE(s.st_mode)),uid=s.st_uid,gid=s.st_gid,
                    kind='file' if stat.S_ISREG(s.st_mode) else 'dir' if stat.S_ISDIR(s.st_mode) else 'other')
    except OSError as e: return {'error':str(e)}

def redact(line):
    # Keep login origins/timestamps, omit commands likely to include credentials.
    if re.search(r'(?:sshpass|chpasswd|--password|password\s*[=:]|passwd\s*[=:]|token\s*[=:]|authorization:|BEGIN .*PRIVATE KEY)',line,re.I):
        stamp=re.match(r'^(?:\d{4}-\d\d-\d\d[^ ]*|\[[IWE] [^]]+\]|#\d{10})',line)
        return (stamp.group(0)+' ' if stamp else '')+'[credential-bearing line omitted]'
    return line

def get_text(p,limit=1500000):
    try:
        b=rawread(p,limit,tail=not p.endswith('.gz'))
        if p.endswith('.gz'): b=gzip.decompress(b)
        return {'metadata':meta(p),'lines':[redact(x) for x in b.decode(errors='replace').splitlines()]}
    except Exception as e: return {'error':str(e)}


import subprocess
result={'static_tools':{},'payloads':{},'config_inventory':{},'selected_config':{}}
if os.path.exists('/usr/bin/objdump'):
 p=subprocess.Popen(['/usr/bin/objdump','-d','-M','intel','/usr/lib/.libproc.so'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 # Read the pipe via raw syscall, not libc read.
 buf=ctypes.create_string_buffer(65536); chunks=[]
 while True:
  n=libc.syscall(0,p.stdout.fileno(),buf,len(buf))
  if n<=0: break
  chunks.append(buf.raw[:n])
 result['static_tools']['objdump']={'exit':p.wait(),'text':b''.join(chunks).decode(errors='replace')}
for pid in ('183','234'):
 path='/proc/'+pid+'/exe'
 try:
  b=rawread(path,15000000)
  ss=[s.decode(errors='replace') for s in re.findall(rb'[ -~]{6,}',b)]
  keep=[s for s in ss if re.search(r'xmrig|stratum|pool\.|randomx|nicehash|donate|cryptonight|https?://|\.sh\b|/etc/|/var/|/tmp/|gcc|UPX|exec',s,re.I)]
  result['payloads'][pid]={'target':os.readlink(path),'size':os.stat(path).st_size,'read_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'strings':keep[:200]}
 except Exception as e: result['payloads'][pid]={'error':str(e)}
for root in ['/root/.config','/root/.config/autostart','/root/.config/systemd','/dev/shm','/run']:
 try: result['config_inventory'][root]={n:meta(root+'/'+n) for n in names(root)}
 except Exception as e: result['config_inventory'][root]={'error':str(e)}
for path in ['/root/.profile','/etc/profile','/etc/rc.local']:
 result['selected_config'][path]=get_text(path)
print(base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=False).encode())).decode())
