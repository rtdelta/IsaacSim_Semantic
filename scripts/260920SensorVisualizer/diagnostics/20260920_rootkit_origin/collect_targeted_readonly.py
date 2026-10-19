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


result={'files':{},'read_pairs':{},'procps':{}}
for p in ['/usr/lib/.ldconfig.aux','/.local/lib/.ldconfig.aux','/root/.local/lib/.ldconfig.aux','/dev/shm/.dbus_lk','/dev/shm/.dbus_pid','/dev/shm/.dbus_sess','/dev/shm/.libproc_h','/dev/shm/.dpkg_journal.pid','/tmp/.cache.lck','/var/log/secure','/var/log/cron']:
 d={'metadata':meta(p)}
 try:
  b=rawread(p,1000000)
  d.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),base64=base64.b64encode(b).decode())
 except Exception as e:d['error']=str(e)
 result['files'][p]=d
for p in ['/usr/lib/python3/dist-packages/psutil/_pslinux.py','/usr/lib/python3/dist-packages/psutil/__pycache__/_pslinux.cpython-312.pyc']:
 d={}
 try:
  b=rawread(p,200000)
  with open(p,'rb') as f: n=f.read()
  d={'raw':base64.b64encode(b).decode(),'normal':base64.b64encode(n).decode()}
 except Exception as e:d={'error':str(e)}
 result['read_pairs'][p]=d
try:
 for n in names('/root/.config/procps'):
  p='/root/.config/procps/'+n
  result['procps'][p]=get_text(p,100000)
except Exception as e:result['procps']['error']=str(e)
print(base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=False).encode())).decode())
