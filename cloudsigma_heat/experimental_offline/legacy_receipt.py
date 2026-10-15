"""Read-only, non-authorizing legacy visibility. Never writes/migrates a record."""
import hashlib,re
from .admission_wire import strict
from .sdk_adapter import canonical

def present(raw):
    result={'schema':'quarantine','obligation':'UNKNOWN','escalate':True,
            'operations_allowed':False,'live_enabled':False,'reason':'unidentified-legacy-or-invalid-record'}
    if type(raw) is not str:return result
    try:
        encoded=raw.encode('utf-8',errors='strict')
        # Reference only, never raw data/error/identity in operator output.
        result['evidence_sha256']=hashlib.sha256(encoded).hexdigest()
        if len(encoded)>4096:return result
        v=strict(encoded)
        keys={'version','wire','binding','account','run','deadline','cleanup_deadline','source','phase','id','calls','escalate'}
        if type(v) is not dict or set(v)!=keys:return result
        if type(v['version']) is not int or v['version']!=1:return result
        if any(type(v[k]) is not str for k in ('wire','binding','account','run','source','phase','id')):return result
        if any(re.fullmatch('[0-9a-f]{64}',v[k]) is None for k in ('wire','binding','source')):return result
        if not canonical(v['account']) or not canonical(v['run']):return result
        if any(type(v[k]) is not int for k in ('deadline','cleanup_deadline','calls')):return result
        if not 0<v['deadline']<v['cleanup_deadline']<=v['deadline']+60 or v['cleanup_deadline']>253402300799 or not 0<=v['calls']<=8:return result
        if v['phase'] not in ('create-uncertain','created','delete-uncertain','absent') or type(v['escalate']) is not bool:return result
        if v['escalate']!=(v['phase']!='absent'):return result
        if (v['phase']=='create-uncertain' and v['id']!='') or (v['phase']!='create-uncertain' and not canonical(v['id'])):return result
        # Valid historical shape cannot authenticate its old binding without the
        # original protected payload. Never attribute ownership or claim absence.
        result.update(schema='legacy-v1',reason='legacy-authority-not-admitted',
                      historical_phase=v['phase'],historical_absence_observation=v['phase']=='absent')
        return result
    except Exception:return result
