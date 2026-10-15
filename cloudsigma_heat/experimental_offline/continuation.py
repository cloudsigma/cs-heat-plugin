"""Caller-trusted offline custody continuation, not new approval or signed authority."""
import json,hashlib,os
from dataclasses import replace,asdict
from .cleanup import CleanupOnly,validate_grant
from .admission_wire import strict
from .admission_model import Refused

def save_atomic(path,value):
    raw=json.dumps(value,sort_keys=True).encode()
    temporary=path.with_name(path.name+'.pending')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        fd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        if temporary.exists():temporary.unlink()

def checkpoint(cap,r,path,original):
    # Only currently admitted in-memory capability can validate current journal.
    # A stale grant cannot be refreshed from a journal by this function.
    validate_grant(original)
    if type(cap) is not CleanupOnly:raise Refused('continuation capability')
    validate_grant(cap.grant)
    for key,value in asdict(original).items():
        if key!='journal_digest' and getattr(cap.grant,key)!=value:raise Refused('continuation authority drift')
    cap.check(True)
    value=cap.record(r)
    if value['phase'] not in ('delete-uncertain','absent'):raise Refused('continuation phase')
    grant=replace(cap.grant,journal_digest=cap._accepted)
    # Preserve ALL authority/window/resource fields; only custody digest advances.
    save_atomic(path,{'original_grant_sha256':hashlib.sha256(json.dumps(asdict(original),sort_keys=True).encode()).hexdigest(),'grant':asdict(grant)})

def load(original,path):
    validate_grant(original)
    value=read_strict(path)
    expected=hashlib.sha256(json.dumps(asdict(original),sort_keys=True).encode()).hexdigest()
    if type(value) is not dict or set(value)!={'original_grant_sha256','grant'} or value['original_grant_sha256']!=expected:raise Refused('continuation origin')
    candidate=value['grant'];base=asdict(original)
    if type(candidate) is not dict or set(candidate)!=set(base):raise Refused('continuation schema')
    for key in base:
        if key!='journal_digest' and (type(candidate[key]) is not type(base[key]) or candidate[key]!=base[key]):raise Refused('continuation authority drift')
    result=replace(original,journal_digest=candidate['journal_digest'])
    validate_grant(result)
    return result


def read_strict(path):
    # I/O failures remain distinguishable; bound bytes before decoding/parsing.
    with path.open('rb') as stream:raw=stream.read(8193)
    invalid=False
    try:
        if len(raw)>8192:raise ValueError()
        text=raw.decode('utf-8',errors='strict')
        value=strict(raw)
        # Reject escaped surrogate strings anywhere, including unknown keys.
        def check(x):
            if type(x) is str:x.encode('utf-8',errors='strict')
            elif type(x) is dict:
                for k,v in x.items():check(k);check(v)
            elif type(x) is list:
                for v in x:check(v)
        check(value)
    except Exception:invalid=True
    if invalid:raise Refused('continuation invalid')
    return value
