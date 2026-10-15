"""Explicit offline delivery, separate from readonly receipt; no network sink."""
import json,re
from .admission_model import digest,Refused
from .admission_wire import strict
KEY='cloudsigma_escalation_v1'

def _bound(cap,r,route):
    if type(route) is not str or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}',route):raise Refused('route')
    v=cap.record(r) # strict current journal only; never legacy/quarantine presenter
    if v is None or v['phase']=='absent' or not v['escalate']:raise Refused('no unresolved obligation')
    ident=digest({'schema':'heat-escalation/v1','binding':cap.binding,'route':route})
    return v,ident

def _load(r,cap,route,ident):
    raw=r.data().get(KEY)
    if raw is None:return None
    try:
        v=strict(raw.encode())
        if set(v)!={'version','id','binding','route','attempts','ack'} or type(v['version']) is not int or v['version']!=1 or v['id']!=ident or v['binding']!=cap.binding or v['route']!=route or type(v['attempts']) is not int or not 0<=v['attempts']<=3 or type(v['ack']) is not bool:raise ValueError()
        if v['ack'] and not 1<=v['attempts']<=3:raise ValueError()
        return v
    except Exception:raise Refused('outbox refused') from None

def stage(cap,r,route):
    with cap.locked(r):
        _,ident=_bound(cap,r,route)
        v=_load(r,cap,route,ident)
        if v is None:
            v=dict(version=1,id=ident,binding=cap.binding,route=route,attempts=0,ack=False)
            r.data_set(KEY,json.dumps(v,sort_keys=True))
        return ident

def deliver(cap,r,route,sink,after_delivery=lambda:None):
    if not callable(sink) or not callable(after_delivery):raise Refused('sink')
    with cap.locked(r):
        _,ident=_bound(cap,r,route);v=_load(r,cap,route,ident)
        if v is None:raise Refused('event not staged')
        if v['ack']:return {'event_id':ident,'ack':True,'live_enabled':False}
        if v['attempts']>=3:raise Refused('attempts exhausted')
        v['attempts']+=1;r.data_set(KEY,json.dumps(v,sort_keys=True))
        # Stable minimal event fields; no journal, resource/account IDs or secret.
        event={'version':1,'event_id':ident,'obligation':'unresolved','route':route}
        try:accepted=sink(event)
        except Exception:raise Refused('delivery pending') from None
        if accepted is not True:raise Refused('delivery pending')
        after_delivery() # deterministic offline crash boundary, no real notifier
        v['ack']=True;r.data_set(KEY,json.dumps(v,sort_keys=True))
        return {'event_id':ident,'ack':True,'live_enabled':False}
