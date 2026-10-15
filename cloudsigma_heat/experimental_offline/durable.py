"""Heat resource-data integration. Offline capability only; no live enable route."""
import hashlib,json,time,uuid
from contextlib import contextmanager
import fcntl,os,stat
from dataclasses import dataclass
from .sdk_adapter import canonical
from pathlib import Path
from heat.db import api as db, models

from .admission_model import Refused
from .admission_wire import validate,strict
KEY='cloudsigma_owned_v1' # existing slot; old version refuses, never virgin reset

def _hash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@dataclass(frozen=True)
class Admission:
    account: str
    run: str
    create_deadline: int
    cleanup_deadline: int
    source: str
    wire: bytes
    window_start: int
    worker: str
    preflight: str
    authority: str
    cleanup_authority: str
    secret_digest: str

class OfflineLifecycle:
    """Injected fake-cloud capability. Production plugin remains disabled by default."""
    def __init__(self,cloud,admission,clock=time.time,cancelled=lambda:False,lock_root=None):
        self.binding,self.logical,self.wire_digest=validate(admission,Admission)
        if admission.source != cloud.trusted_source: raise Refused('trusted source mismatch')
        self._admission=admission;self._wire=admission.wire;self.cloud=cloud;self.lock_root=lock_root;self.clock=clock;self.cancelled=cancelled
    def intact(self):
        b,l,w=validate(self._admission,Admission)
        if b!=self.binding or l!=self.logical or w!=self.wire_digest or self._wire!=self._admission.wire:raise Refused('admission drift')
    @property
    def account(self):return self._admission.account
    @property
    def run(self):return self._admission.run
    @property
    def deadline(self):return self._admission.create_deadline
    def record(self,r):
        self.intact()
        raw=r.data().get(KEY)
        if raw is None:return None
        try:v=strict(raw.encode() if type(raw) is str else raw)
        except Exception:raise Refused('invalid journal') from None
        if type(v) is not dict:raise Refused('invalid journal')
        if set(v)!={'logical','worker','preflight','secret_digest','authority','cleanup_authority','window_start','version','wire','binding','account','run','deadline','cleanup_deadline','source','phase','id','calls','escalate'} or v['binding']!=self.binding or v['account']!=self.account or v['run']!=self.run or type(v['deadline']) is not int or v['deadline']!=self.deadline:raise Refused('binding refused')
        if v['logical']!=self.logical or any(v[k]!=getattr(self._admission,k) or type(v[k]) is not type(getattr(self._admission,k)) for k in ('worker','preflight','secret_digest','authority','cleanup_authority','window_start')):raise Refused('binding')
        if type(v['cleanup_deadline']) is not int or v['cleanup_deadline']!=self._admission.cleanup_deadline or v['source']!=self._admission.source:raise Refused('admission drift')
        if type(v['version']) is not int or v['version']!=2 or v['wire']!=hashlib.sha256(self._wire).hexdigest() or any(type(v[k]) is not str for k in ('wire','binding','account','run','phase','id')):raise Refused('schema')
        if v['phase'] not in ('create-uncertain','created','delete-uncertain','absent') or type(v['calls']) is not int or not 0<=v['calls']<=8 or type(v['escalate']) is not bool:raise Refused('state refused')
        if type(v['id']) is not str:raise Refused('id refused')
        if v['phase']=='create-uncertain' and v['id']:raise Refused('unexpected ID')
        if v['phase']!='create-uncertain':
            try:
                if str(uuid.UUID(v['id']))!=v['id']:raise ValueError()
            except Exception:raise Refused('invalid owned ID') from None
        if v['escalate']!=(v['phase']!='absent'):raise Refused('obligation')
        return v
    def save(self,r,v):r.data_set(KEY,json.dumps(v,sort_keys=True))
    def check(self,cleanup=False):
        self.intact()
        if self.clock()<self._admission.window_start:raise Refused('prewindow')
        if self.cancelled() or self.clock()>=(self._admission.cleanup_deadline if cleanup else self.deadline):raise Refused('expired or cancelled')
    def reserve(self,r,v,cleanup=False):
        self.check(cleanup)
        self.cloud.deadline=self._admission.cleanup_deadline if cleanup else self.deadline
        if v['calls']>=8:raise Refused('budget')
        v['calls']+=1;self.save(r,v)
    @contextmanager
    def locked(self,r):
        # Heat owns engine_id/atomic_key. Never write/clear them here.
        # Offline local-host advisory fence only; kernel releases it on process exit.
        if self.lock_root is None:raise Refused('offline lock root missing')
        root=Path(self.lock_root)
        if root.is_symlink() or root.stat().st_mode & 0o077:raise Refused('unsafe lock root')
        fd=os.open(str(root/('resource-%s.lock'%r.id)),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Refused('resource locked') from None
            fs=os.fstat(fd)
            if not stat.S_ISREG(fs.st_mode) or fs.st_uid!=os.geteuid() or fs.st_nlink!=1 or fs.st_mode&0o077:raise Refused('unsafe lock file')
            r._data=None;yield
        finally:os.close(fd)
    def create(self,r):
        with self.locked(r):
            self.check()
            if r.resource_id or self.record(r) is not None:raise Refused('replay or imported ID')
            v=dict(version=2,logical=self.logical,worker=self._admission.worker,preflight=self._admission.preflight,secret_digest=self._admission.secret_digest,authority=self._admission.authority,cleanup_authority=self._admission.cleanup_authority,window_start=self._admission.window_start,wire=hashlib.sha256(self._wire).hexdigest(),binding=self.binding,account=self.account,run=self.run,deadline=self.deadline,cleanup_deadline=self._admission.cleanup_deadline,source=self._admission.source,phase='create-uncertain',id='',calls=0,escalate=True)
            self.reserve(r,v) # failure here means ZERO cloud dispatch
            reply=self.cloud.create_bytes(self._wire)
            ident=reply.get('uuid') if isinstance(reply,dict) else None
            self.check()
            if not canonical(ident):raise Refused('unknown create ID')
            v.update(id=ident,phase='created');self.save(r,v)
            r.resource_id_set(ident)
            return ident
    def observe(self,r,v,cleanup=False):
        if r.resource_id and r.resource_id!=v['id']:raise Refused('physical ID drift')
        self.reserve(r,v,cleanup)
        value=self.cloud.get(v['id']);self.check(cleanup)
        if value is None and v['phase']=='delete-uncertain':
            v.update(phase='absent',escalate=False);self.save(r,v);return None
        if not isinstance(value,dict) or value.get('uuid')!=v['id'] or value.get('name')!=self.run or (value.get('owner') if type(value.get('owner')) is dict else {}).get('uuid')!=self.account or value.get('status')!='stopped' or any(value.get(k)!=[] for k in ('drives','nics','jobs')):raise Refused('ownership or dependency refused')
        return value
    def delete(self,r):
        with self.locked(r):
            v=self.record(r)
            if v is None:raise Refused('imported or unowned ID')
            if v['phase']=='absent':return None
            if v['phase']!='created' or not v['id'] or (r.resource_id and r.resource_id!=v['id']):raise Refused('uncertain cleanup')
            self.observe(r,v,True);v['phase']='delete-uncertain';self.reserve(r,v,True)
            self.cloud.delete(v['id']) # exact ID, no recursive operation
            return v['id']
    def reconcile(self,r):
        with self.locked(r):
            v=self.record(r)
            if v and v['phase']=='absent':return True
            if not v or not v['id'] or v['phase']!='delete-uncertain':raise Refused('unknown obligation')
            return self.observe(r,v,True) is None
    def receipt(self,r):
        r._data=None
        try:v=self.record(r)
        except Refused:
            from .legacy_receipt import present
            return present(r.data().get(KEY))
        if v is None:raise Refused('no obligation')
        return {'phase':v['phase'],'expired':self.clock()>=v['deadline'],'escalate':v['escalate'],'deadline':v['deadline'],'live_enabled':False}

    def complete(self,r):
        with self.locked(r):
            v=self.record(r)
            if not v or v['phase']!='created' or r.resource_id!=v['id']:raise Refused('completion ownership')
            if v['calls']>=2:raise Refused('cleanup reserve')
            return self.observe(r,v) is not None
