"""Heat-specific versioned binding; accepted pure canonical model reused unchanged."""
import json,hashlib
from dataclasses import fields
from .admission_model import digest,Refused

def strict(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise Refused('wire')
            out[k]=v
        return out
    if type(raw) is not bytes or not 0<len(raw)<=8192:raise Refused('wire')
    try:
        obj=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(Refused('wire')))
        digest(obj) # bounded types/depth/integer/nonfinite policy
        return obj
    except Exception:raise Refused('wire') from None

def validate(a,cls):
    if type(a) is not cls or any(f.name not in vars(a) for f in fields(cls)):raise Refused('schema')
    for f in fields(cls):
        if type(getattr(a,f.name)) is not f.type:raise Refused('field_type')
    from .sdk_adapter import canonical
    if not canonical(a.account) or not canonical(a.run):raise Refused('identity')
    if not 0<a.window_start<a.create_deadline<a.cleanup_deadline<=a.create_deadline+60 or a.create_deadline-a.window_start>60:raise Refused('window')
    for s in (a.source,a.worker,a.preflight,a.secret_digest):
        if len(s)!=64 or any(c not in '0123456789abcdef' for c in s):raise Refused('digest')
    for s in (a.authority,a.cleanup_authority):
        if not s.strip() or len(s)>256 or any(ord(c)<32 or ord(c)==127 for c in s):raise Refused('authority')
    value=strict(a.wire)
    if type(value) is not dict or set(value)!={'objects'} or type(value['objects']) is not list or len(value['objects'])!=1:raise Refused('payload')
    x=value['objects'][0]
    if type(x) is not dict or set(x)!={'cpu','mem','name','vnc_password','drives','nics'}:raise Refused('payload')
    if x['name']!=a.run or type(x['cpu']) is not int or type(x['mem']) is not int or not 0<x['cpu']<=2**63-1 or not 0<x['mem']<=2**63-1:raise Refused('resources')
    if type(x['drives']) is not list or x['drives'] or type(x['nics']) is not list or x['nics']:raise Refused('dependencies')
    secret=x['vnc_password']
    if type(secret) is not str or not 16<=len(secret)<=128 or any(not 33<=ord(c)<=126 for c in secret):raise Refused('secret')
    if hashlib.sha256(secret.encode()).hexdigest()!=a.secret_digest:raise Refused('secret_digest')
    logical=digest(value);wire=hashlib.sha256(a.wire).hexdigest()
    binding=digest({'schema':'heat-one-server/v2','account':a.account,'run':a.run,'source':a.source,'worker':a.worker,'preflight':a.preflight,'authority':a.authority,'cleanup_authority':a.cleanup_authority,'window_start':a.window_start,'create_deadline':a.create_deadline,'cleanup_deadline':a.cleanup_deadline,'logical':logical,'wire':wire,'secret_digest':a.secret_digest})
    return binding,logical,wire
