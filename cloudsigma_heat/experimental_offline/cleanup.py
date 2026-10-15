"""Offline cleanup-only delegation. No admission wire or secret material required.
Caller-issued grant is NOT authenticated operational authority. Never issue from
journal alone: issuer must independently retain approved binding and digests.
"""
import hashlib, json
from dataclasses import dataclass, fields
from .admission_model import Refused, digest
from .admission_wire import strict
from .durable import OfflineLifecycle, KEY
from .sdk_adapter import canonical

@dataclass(frozen=True)
class CleanupGrant:
    account: str
    run: str
    source: str
    worker: str
    preflight: str
    authority: str
    cleanup_authority: str
    window_start: int
    create_deadline: int
    cleanup_deadline: int
    logical: str
    wire: str
    secret_digest: str
    binding: str
    journal_digest: str
    resource: int
    stack: str

class CleanupOnly(OfflineLifecycle):
    def __init__(self, cloud, grant, clock, lock_root, cancelled=lambda:False):
        self.grant=grant;self.cloud=cloud;self.clock=clock;self.lock_root=lock_root;self.cancelled=cancelled
        self._identity=self._validate()
        self._accepted=grant.journal_digest
    def _validate(self):
        identity=validate_grant(self.grant)
        if self.grant.source != self.cloud.trusted_source: raise Refused('trusted source mismatch')
        return identity
    def intact(self):
        if self._validate()!=self._identity:raise Refused('cleanup grant drift')
    @property
    def binding(self):
        """Read-only original grant binding; never infer authority from storage."""
        self.intact()
        return self.grant.binding
    @property
    def account(self):return self.grant.account
    @property
    def run(self):return self.grant.run
    def check(self,cleanup=False):
        self.intact()
        if not cleanup:raise Refused('cleanup only')
        if self.cancelled() or not self.grant.window_start<=self.clock()<self.grant.cleanup_deadline:raise Refused('cleanup expired or cancelled')
    def create(self,r):raise Refused('cleanup cannot create')
    def complete(self,r):raise Refused('cleanup cannot complete create')
    def record(self,r):
        self.intact()
        if r.id!=self.grant.resource or r.stack.id!=self.grant.stack:raise Refused('cleanup resource binding')
        raw=r.data().get(KEY)
        if type(raw) is not str:raise Refused('cleanup journal missing')
        invalid=False
        try:
            encoded=raw.encode('utf-8',errors='strict')
            v=strict(encoded)
        except Exception:
            invalid=True
        # Raise after leaving except: no retained parser/encoding exception context.
        if invalid:raise Refused('cleanup journal invalid')
        if hashlib.sha256(encoded).hexdigest()!=self._accepted:raise Refused('cleanup journal drift')
        a=self.grant
        keys={'logical','worker','preflight','secret_digest','authority','cleanup_authority','window_start','version','wire','binding','account','run','deadline','cleanup_deadline','source','phase','id','calls','escalate'}
        if type(v) is not dict or set(v)!=keys:raise Refused('cleanup journal schema')
        for key in keys-{'version','deadline','phase','id','calls','escalate'}:
            expected=getattr(a,key)
            if type(v[key]) is not type(expected) or v[key]!=expected:raise Refused('cleanup journal binding')
        if type(v['deadline']) is not int or v['deadline']!=a.create_deadline or type(v['version']) is not int or v['version']!=2:raise Refused('cleanup journal version')
        if type(v['phase']) is not str or v['phase'] not in ('created','create-uncertain','delete-uncertain','absent') or type(v['calls']) is not int or not 0<=v['calls']<=8 or type(v['escalate']) is not bool or v['escalate']!=(v['phase']!='absent'):raise Refused('cleanup journal state')
        if (v['phase']=='create-uncertain' and v['id']!='') or (v['phase']!='create-uncertain' and not canonical(v['id'])):raise Refused('cleanup journal ID')
        return v
    def save(self,r,v):
        raw=json.dumps(v,sort_keys=True)
        r.data_set(KEY,raw)
        r._data=None
        if r.data().get(KEY)!=raw:raise Refused('cleanup storage readback')
        self._accepted=hashlib.sha256(raw.encode()).hexdigest()
    def reserve(self,r,v,cleanup=False):
        self.check(cleanup)
        self.cloud.deadline=self.grant.cleanup_deadline
        if v['calls']>=8:raise Refused('budget')
        v['calls']+=1;self.save(r,v)

def validate_grant(a):
    if type(a) is not CleanupGrant or any(f.name not in vars(a) or type(getattr(a,f.name)) is not f.type for f in fields(CleanupGrant)):raise Refused('cleanup schema')
    if not canonical(a.account) or not canonical(a.run) or not canonical(a.stack) or a.resource<=0:raise Refused('cleanup identity')
    if not 0<a.window_start<a.create_deadline<a.cleanup_deadline<=a.create_deadline+60 or a.create_deadline-a.window_start>60:raise Refused('cleanup window')
    for key in ('source','worker','preflight','logical','wire','secret_digest','binding','journal_digest'):
        value=getattr(a,key)
        if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise Refused('cleanup digest')
    for value in (a.authority,a.cleanup_authority):
        if not value.strip() or len(value)>256 or any(ord(c)<32 or ord(c)==127 for c in value):raise Refused('cleanup authority')
    binding=digest(dict(schema='heat-one-server/v2',account=a.account,run=a.run,source=a.source,worker=a.worker,preflight=a.preflight,authority=a.authority,cleanup_authority=a.cleanup_authority,window_start=a.window_start,create_deadline=a.create_deadline,cleanup_deadline=a.cleanup_deadline,logical=a.logical,wire=a.wire,secret_digest=a.secret_digest))
    if binding!=a.binding:raise Refused('cleanup binding')
    return digest(vars(a))
