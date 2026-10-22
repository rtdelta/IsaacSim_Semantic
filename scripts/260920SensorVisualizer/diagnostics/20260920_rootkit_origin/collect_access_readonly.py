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


result={'ssh_keys':{},'history':{},'hidden_files':{}}
p='/root/.ssh/authorized_keys'
try:
 b=rawread(p,200000); ks=[]
 for line in b.decode(errors='replace').splitlines():
  match=re.search(r'(ssh-(?:rsa|ed25519)|ecdsa-sha2-\S+)\s+([A-Za-z0-9+/=]+)',line)
  if match:
   digest=hashlib.sha256(base64.b64decode(match.group(2))).digest()
   ks.append({'type':match.group(1),'fingerprint':'SHA256:'+base64.b64encode(digest).decode().rstrip('=')})
 result['ssh_keys']={'metadata':meta(p),'fingerprints':ks}
except Exception as e: result['ssh_keys']={'error':str(e)}
for p in ['/root/.ipython/profile_default/history.sqlite','/root/.ipython/profile_default/history.sqlite-wal','/root/.ipython/profile_default/history.sqlite-shm']:
 m=meta(p);result['history'][p]={'metadata':m}
 if m.get('kind')=='file' and m['size']<10000000:
  b=rawread(p,10000000);result['history'][p]['base64']=base64.b64encode(b).decode()
for root in ['/dev/shm','/usr/lib','/root/.local/lib','/run']:
 try:
  for n in names(root):
   if n.startswith('.') or any(x in n for x in ['libproc','dpkg_journal','ldconfig.aux','polkitdl','nvidian']):
    result['hidden_files'][root+'/'+n]=meta(root+'/'+n)
 except OSError:pass
print(base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=False).encode())).decode())
