import sys,json,traceback

def guard(event,args):
    if (event.startswith('socket.') and event!='socket.gethostname') or event in ('subprocess.Popen','os.system','os.fork','os.posix_spawn','os.exec'):raise PermissionError('offline guard')
sys.addaudithook(guard)
import requests
from cloudsigma_heat.experimental_offline.sdk_adapter import SDKCloud
from cloudsigma_heat.experimental_offline.cleanup import CleanupGrant,validate_grant
from cloudsigma_heat.experimental_offline.admission_model import Refused
from dataclasses import fields
class Fake(requests.adapters.BaseAdapter):
    def close(self):pass
    def send(self,*a,**kw):raise requests.ConnectionError('secret-sentinel')
args=dict(endpoint='https://offline.invalid/api/2.0/',username='user',password='password',trusted_source='a'*64,offline_opt_in=True)
count=0
for key in args:
    a=args.copy();del a[key]
    try:SDKCloud(Fake(),**a)
    except TypeError:count+=1
    else:raise AssertionError(key)
for key in ('endpoint','username','password','trusted_source'):
    for value in (None,True,12,[],{}):
        a=args|{key:value}
        try:SDKCloud(Fake(),**a)
        except (ValueError,TypeError):count+=1
        else:raise AssertionError((key,value))
for f in fields(CleanupGrant):
    g=object.__new__(CleanupGrant)
    for other in fields(CleanupGrant):
        if other.name!=f.name:object.__setattr__(g,other.name,0 if other.type is int else '')
    try:validate_grant(g)
    except Refused as e:assert str(e)=='cleanup schema';count+=1
    else:raise AssertionError(f.name)
with SDKCloud(Fake(),clock=lambda:100,**args) as c:
    c.deadline=110
    try:c.get('33333333-3333-3333-3333-333333333333')
    except Exception as e:
        rendered=''.join(traceback.format_exception(e))
        assert str(e)=='transport' and 'secret-sentinel' not in rendered
        context_retained=e.__context__ is not None and 'secret-sentinel' in str(e.__context__)
    else:raise AssertionError('transport')
print(json.dumps(dict(refusal_cases_passed=count,transport_display_redacted=True,transport_exception_context_retained=context_retained,network_attempts=0)))
