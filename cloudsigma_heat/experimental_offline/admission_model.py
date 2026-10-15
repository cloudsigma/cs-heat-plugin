"""Offline one-server admission model. No network, credentials loader or allocator."""
from dataclasses import dataclass, asdict, fields
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

class Refused(Exception):
    """Only stable sanitized codes are emitted."""

def need(ok, code):
    if not ok: raise Refused(code)
def digest(value):
    # Versioned UTF-8, ASCII escaping, sorted keys; no float coercion or normalization.
    def check(x, depth=0):
        need(depth<=12, 'canonical')
        if type(x) is str:
            need(len(x)<=1024 and not any(0xD800<=ord(c)<=0xDFFF for c in x), 'canonical')
        elif type(x) is int: need(abs(x)<=2**63-1, 'canonical')
        elif type(x) is bool or x is None: pass
        elif type(x) in (list,tuple):
            need(len(x)<=128, 'canonical')
            for item in x: check(item,depth+1)
        elif type(x) is dict:
            need(len(x)<=128 and all(type(k) is str for k in x), 'canonical')
            for k,v in x.items(): check(k,depth+1);check(v,depth+1)
        else: raise Refused('canonical')
    try:
        check(value)
        raw=json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
        need(len(raw)<=65536, 'canonical')
        return hashlib.sha256(b'one-server-admission/v2\0'+raw).hexdigest()
    except Refused: raise
    except (ValueError,TypeError,OverflowError,RecursionError,UnicodeError):
        raise Refused('canonical') from None
def hex64(x): return type(x) is str and re.fullmatch('[0-9a-f]{64}', x) is not None
def uuid(x): return type(x) is str and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', x) is not None

@dataclass(frozen=True)
class Preflight:
    account: str
    authorization: str
    evidence: str
    observed_at: int
    expires_at: int
    cpu_type: str
    cpu_min: int
    cpu_max: int
    cpu_step: int
    memory_min: int
    memory_max: int
    memory_step: int
    server_slots: int
    cpu_headroom: int
    memory_headroom: int

@dataclass(frozen=True)
class Admission:
    account: str
    run: str
    source: str
    worker_digest: str
    preflight_digest: str
    approval_reference: str
    currency: str
    maximum_exposure: str
    window_start: int
    deadline: int
    cleanup_owner: str
    escalation_reference: str
    accepts_billing_uncertainty: bool
    charging_evidence: str
    cpu: int
    memory: int
    cpu_type: str
    secret_reference: str
    secret_digest: str
    payload_digest: str

@dataclass(frozen=True)
class Receipt:
    admission_digest: str
    account: str
    run: str
    deadline: int
    phase: str
    owned_id: str
    absence_observed: bool


def validate(a, p, *, now, expected_account, expected_source, expected_worker,
             preflight_authorization, expected_admission, obligation=None):
    record(a, Admission); record(p, Preflight); epoch(now)
    need(uuid(expected_account) and all(hex64(x) for x in (expected_source,expected_worker,preflight_authorization,expected_admission)), 'expected_binding')
    if obligation is not None: record(obligation, Receipt)
    need(type(now) is int, 'clock')
    need(uuid(a.account) and uuid(a.run) and a.account == p.account == expected_account, 'account')
    need(hex64(expected_source) and a.source == expected_source and hex64(expected_worker) and a.worker_digest == expected_worker, 'source')
    need(hex64(preflight_authorization) and p.authorization == preflight_authorization, 'preflight_authority')
    need(hex64(p.evidence) and a.preflight_digest == digest(asdict(p)), 'evidence')
    need(all(type(v) is int for v in (p.observed_at,p.expires_at,a.window_start,a.deadline)), 'time_type')
    need(p.observed_at <= now < p.expires_at and now-p.observed_at <= 300, 'stale_preflight')
    need(a.window_start <= now < a.deadline <= p.expires_at and 0 < a.deadline-a.window_start <= 60, 'deadline')
    need(all(type(x) is str and x.strip() and not any(ord(c)<32 or ord(c)==127 for c in x) for x in (a.approval_reference,a.cleanup_owner,a.escalation_reference,a.secret_reference)), 'approval')
    need(type(a.accepts_billing_uncertainty) is bool and (hex64(a.charging_evidence) or a.accepts_billing_uncertainty), 'billing_decision')
    need(type(a.currency) is str and re.fullmatch('[A-Z]{3}',a.currency) is not None, 'currency')
    need(type(a.maximum_exposure) is str and re.fullmatch(r'[0-9]+(\.[0-9]+)?',a.maximum_exposure) is not None, 'exposure')
    try: amount=Decimal(a.maximum_exposure)
    except InvalidOperation: raise Refused('exposure') from None
    need(amount.is_finite() and amount>0, 'exposure')
    need(type(a.cpu_type) is str and a.cpu_type and a.cpu_type==p.cpu_type, 'cpu_type')
    for value,lo,hi,step,head in ((a.cpu,p.cpu_min,p.cpu_max,p.cpu_step,p.cpu_headroom),(a.memory,p.memory_min,p.memory_max,p.memory_step,p.memory_headroom)):
        need(all(type(x) is int for x in (value,lo,hi,step,head)) and 0<lo<=hi and step>0 and lo<=value<=hi and (value-lo)%step==0 and value<=head, 'legal_resources')
    need(type(p.server_slots) is int and p.server_slots>=1, 'quota')
    need(hex64(a.secret_digest) and hex64(a.payload_digest), 'payload_binding')
    need(hex64(expected_admission) and digest(asdict(a))==expected_admission, 'admission_drift')
    # Even a completed earlier receipt cannot authorize replay of this single run.
    need(obligation is None, 'existing_obligation')
    return expected_admission


def payload(a, p, secret, **checks):
    """Transient sensitive payload only; never a log or durable receipt value.

    Secret bytes supplied from protected caller memory; no generation/load here.
    Secret policy/charset is an explicit offline policy, not provider approval.
    """
    validate(a,p,**checks)
    need(type(secret) is bytes and 16<=len(secret)<=128 and all(33<=x<=126 for x in secret), 'secret_policy')
    need(hashlib.sha256(secret).hexdigest()==a.secret_digest, 'secret_drift')
    result={'objects':[{'cpu':a.cpu,'mem':a.memory,'cpu_type':a.cpu_type,'name':a.run,'vnc_password':secret.decode('ascii'),'drives':[],'nics':[]}]}
    need(digest(result)==a.payload_digest, 'payload_drift')
    return result


def consumer_id(a, receipt, *, now, consumer):
    """Pure ID handoff; does NOT invoke a driver, refresh, or API method."""
    record(a, Admission); record(receipt, Receipt); epoch(now)
    need(type(consumer) is str and consumer in ('machine.GetState','heat.selected_read','terraform.scoped_refresh'), 'consumer')
    need(type(receipt) is Receipt and receipt.admission_digest==digest(asdict(a)) and receipt.account==a.account and receipt.run==a.run and receipt.deadline==a.deadline, 'receipt_binding')
    need(type(now) is int and a.window_start<=now<a.deadline, 'expired')
    need(receipt.phase=='owned-observed' and uuid(receipt.owned_id) and receipt.absence_observed is False, 'ownership')
    return receipt.owned_id


def present(receipt, now):
    """Redacted local status; no IDs/secrets or deadline renewal/reset."""
    record(receipt, Receipt); epoch(now)
    need(receipt.phase in ('create-uncertain','owned-observed','delete-uncertain','absence-observed'), 'phase')
    need(type(receipt.absence_observed) is bool and (receipt.phase=='absence-observed')==receipt.absence_observed, 'absence')
    return {'admission_digest':receipt.admission_digest,'deadline':receipt.deadline,
            'expired':now>=receipt.deadline,'phase':receipt.phase,
            'obligation':'closed' if receipt.absence_observed else 'escalate',
            'allocation_authorized':False}

@dataclass(frozen=True)
class AllocationAuthorization:
    admission_digest: str
    authorization_reference: str
    account: str
    deadline: int


def allocation_prerequisite(a, authorization, *, now):
    """Pure separate prerequisite check, NEVER an allocator or live enablement.

    References are trusted caller inputs, not signatures/identity verification.
    Operational caller must independently verify actual owner authority.
    """
    record(a, Admission); record(authorization, AllocationAuthorization); epoch(now)
    need(authorization.admission_digest==digest(asdict(a)) and authorization.account==a.account and authorization.deadline==a.deadline, 'allocation_binding')
    need(type(authorization.authorization_reference) is str and bool(authorization.authorization_reference.strip()), 'allocation_authority_missing')
    need(type(now) is int and a.window_start<=now<a.deadline, 'expired')
    return {'schema_prerequisite_satisfied':True,'live_enabled':False}


def epoch(value):
    need(type(value) is int and 0<value<=253402300799, 'time')


def record(value, cls):
    """Complete runtime field validation BEFORE comparison/asdict/hash/output."""
    need(cls in (Preflight,Admission,Receipt,AllocationAuthorization) and type(value) is cls, 'schema')
    # Check completeness before reading any field value or applying invariants.
    need(all(f.name in vars(value) for f in fields(cls)), 'schema')
    for f in fields(cls):
        x=getattr(value,f.name)
        need(type(x) is f.type, 'field_type')
        if f.type is str:
            need(len(x)<=256 and not any(ord(c)<32 or ord(c)==127 or 0xD800<=ord(c)<=0xDFFF for c in x), 'field_text')
        elif f.type is int: need(0<=x<=2**63-1, 'field_integer')
    for name in ('account','run'):
        if hasattr(value,name): need(uuid(getattr(value,name)), 'identity')
    for name in ('source','worker_digest','preflight_digest','secret_digest','payload_digest','admission_digest','authorization','evidence'):
        if hasattr(value,name): need(hex64(getattr(value,name)), 'digest')
    for name in ('observed_at','expires_at','window_start','deadline'):
        if hasattr(value,name): epoch(getattr(value,name))
    for name in ('approval_reference','cleanup_owner','escalation_reference','secret_reference','authorization_reference','cpu_type'):
        if hasattr(value,name): need(bool(getattr(value,name).strip()), 'reference')
    if cls is Preflight:
        need(value.observed_at<value.expires_at, 'preflight_window')
        for lo,hi,step in ((value.cpu_min,value.cpu_max,value.cpu_step),(value.memory_min,value.memory_max,value.memory_step)):
            need(0<lo<=hi and step>0, 'resource_range')
    elif cls is Admission:
        need(0<value.deadline-value.window_start<=60, 'window')
        need(value.cpu>0 and value.memory>0, 'resources')
        need(re.fullmatch('[A-Z]{3}',value.currency) is not None, 'currency')
        need(len(value.maximum_exposure)<=64 and re.fullmatch(r'[0-9]+(\.[0-9]+)?',value.maximum_exposure) is not None, 'exposure')
        need(Decimal(value.maximum_exposure)>0, 'exposure')
        need((value.charging_evidence=='' or hex64(value.charging_evidence)) and (value.accepts_billing_uncertainty or hex64(value.charging_evidence)), 'billing')
    elif cls is Receipt:
        need(value.phase in ('create-uncertain','owned-observed','delete-uncertain','absence-observed'), 'phase')
        need((value.phase=='create-uncertain' and value.owned_id=='') or (value.phase!='create-uncertain' and uuid(value.owned_id)), 'ownership')
        need(value.absence_observed==(value.phase=='absence-observed'), 'absence')
