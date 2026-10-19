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

result={'collected_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{},'directories':{},'logs':{},'processes':{},'artifacts':{},'network':{}}
paths=['/usr/lib/.libproc.so','/var/lib/.dpkg-triggers-2890','/etc/ld.so.preload','/etc/cron.d/apt-compat','/etc/rc.local','/var/spool/cron/crontabs/root','/root/.bash_history','/root/.zsh_history','/root/.wget-hsts','/etc/ssh/sshd_config','/var/log/wtmp','/var/log/btmp','/var/log/lastlog']
for p in paths: result['files'][p]=meta(p)
for p in ['/usr/lib/.libproc.so','/var/lib/.dpkg-triggers-2890']:
    try:
        b=rawread(p,1000000)
        result['artifacts'][p]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'base64':base64.b64encode(b).decode()}
    except Exception as e: result['artifacts'][p]={'error':str(e)}
for p in ['/var/log','/var/log/apt','/var/log/audit','/var/log/journal','/run/log/journal','/tmp','/var/tmp','/root','/var/lib','/etc/cron.d','/etc/ssh/sshd_config.d']:
    try: result['directories'][p]={n:meta(p+'/'+n) for n in names(p)}
    except Exception as e: result['directories'][p]={'error':str(e)}
logpaths=['/root/.bash_history','/root/.zsh_history','/root/.wget-hsts','/etc/ld.so.preload','/etc/cron.d/apt-compat','/etc/rc.local','/var/spool/cron/crontabs/root','/etc/ssh/sshd_config','/var/log/auth.log','/var/log/syslog','/var/log/selkies.log','/tmp/.desktop.log','/var/log/xorg.log']
for root,entries in result['directories'].items():
    for n,m in entries.items():
        if not isinstance(m,dict) or m.get('kind')!='file': continue
        if root=='/var/log/apt' or (root=='/var/log' and re.match(r'(auth\.log|syslog|dpkg\.log|cloud-init|supervisord|jupyter|sshd)',n)) or root=='/etc/ssh/sshd_config.d': logpaths.append(root+'/'+n)
for p in sorted(set(logpaths)): result['logs'][p]=get_text(p,5000000)
for p in ['/proc/net/tcp','/proc/net/tcp6','/proc/net/udp','/proc/net/udp6']:
    result['network'][p]=get_text(p,200000)
for pid in names('/proc'):
    if not pid.isdigit(): continue
    try:
        comm=rawread('/proc/'+pid+'/comm',512).decode().strip()
        exe=os.readlink('/proc/'+pid+'/exe')
        if pid=='1' or any(x in comm+' '+exe for x in ['.dpkg-triggers','polkitdl','nvidian','supervisord','sshd','jupyter','gpufree','selkies']):
            d={'comm':comm,'exe':exe,'stat':rawread('/proc/'+pid+'/stat',8192).decode(),
               'cmdline':redact(rawread('/proc/'+pid+'/cmdline',20000).decode(errors='replace').replace('\0',' ')),
               'fds':{},'logs':{}}
            for f in names('/proc/'+pid+'/fd'):
                path='/proc/'+pid+'/fd/'+f
                try:
                    target=os.readlink(path); d['fds'][f]=target
                    if ('/var/log/' in target or target=='/tmp/.desktop.log') and stat.S_ISREG(os.stat(path).st_mode): d['logs'][f]=get_text(path,2000000)
                except OSError: pass
            result['processes'][pid]=d
    except (OSError,ValueError): pass
for p in ['/var/log/wtmp','/var/log/btmp']:
    try:
        b=rawread(p,2000000,tail=True)
        result['artifacts'][p]={'base64':base64.b64encode(b).decode(),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception as e: result['artifacts'][p]={'error':str(e)}
print(base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=False).encode())).decode())
