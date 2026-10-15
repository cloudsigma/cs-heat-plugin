"""Run with -I from outside the checkout against an installed wheel."""
import sys, os, json, hashlib, io, tempfile, unittest, importlib
from pathlib import Path

def deny(event,args):
    if (event.startswith('socket.') and event!='socket.gethostname') or event in ('subprocess.Popen','os.system','os.fork','os.forkpty','os.posix_spawn','os.exec'):
        raise PermissionError('offline guard')
sys.addaudithook(deny)
from oslo_config import cfg
from heat.common import context
from heat.db import api, models
from heat.engine import stack, template, rsrc_defn
from dataclasses import asdict, replace, fields
import requests
from cloudsigma_heat.experimental_offline import cleanup, durable, outbox, plugin, early_admission, resource_mapping, registry_adapter, continuation
from cloudsigma_heat.experimental_offline.sdk_adapter import SDKCloud
from cloudsigma_heat.experimental_offline.admission_model import Refused

ACCOUNT='11111111-1111-1111-1111-111111111111'; RUN='22222222-2222-2222-2222-222222222222'; ID='33333333-3333-3333-3333-333333333333'
ENDPOINT='https://offline.invalid/api/2.0/'; SOURCE=hashlib.sha256(b'caller-reviewed-source').hexdigest(); SECRET='test-only-VNC-value'
class Raw(io.BytesIO):
    def read(self,n=-1,decode_content=False):return super().read(n)
    def release_conn(self):pass
class FakeHTTP(requests.adapters.BaseAdapter):
    def __init__(self):self.calls=[];self.absent=False
    def close(self):pass
    def send(self,q,**kw):
        assert q.url==ENDPOINT+'servers/'+('' if q.method=='POST' else ID+'/')
        self.calls.append(q.method)
        value=dict(uuid=ID,name=RUN,owner={'uuid':ACCOUNT},status='stopped',drives=[],nics=[],jobs=[])
        r=requests.Response();r.url=q.url;r.request=q;r.status_code=200
        if q.method=='POST':r.status_code=201;value={'objects':[value]}
        if q.method=='DELETE':r.status_code=204;self.absent=True
        if q.method=='GET' and self.absent:r.status_code=404
        r.headers={'Content-Type':'application/json'};r.raw=Raw(json.dumps(value).encode());return r

class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cfg.CONF([],project='heat',default_config_files=[])
        cfg.CONF.set_override('connection','sqlite:///'+str(cls.root/'db.sqlite'),group='database')
        cfg.CONF.set_override('deferred_auth_method','password')
        models.BASE.metadata.create_all(api.get_engine())
    def cloud(self,**kw):
        args=dict(endpoint=ENDPOINT,username='test-user',password='test-password',trusted_source=SOURCE,offline_opt_in=True);args.update(kw)
        return SDKCloud(FakeHTTP(),clock=lambda:100,**args)
    def test_combined_native_cleanup_outbox(self):
        ctx=context.RequestContext(username='protected:actor',user_id='fixture',project_id='fixture',is_admin=True)
        props={role:'protected:'+ACCOUNT+':'+role+':test' for role in ('username','password','vnc_password')};props['api_endpoint']=ENDPOINT
        doc={'heat_template_version':'2018-08-31','resources':{'server':{'type':'CloudSigma::Compute::Instance','properties':props}}}
        tid=early_admission.store(json.dumps(doc).encode(),ACCOUNT,ctx,endpoint=ENDPOINT)
        st=stack.Stack(ctx,'offline-package',template.Template.load(ctx,tid),disable_rollback=True,convergence=True);st.store()
        rd=rsrc_defn.ResourceDefinition('server','CloudSigma::Compute::Instance',properties=props)
        r=plugin.CloudSigmaCompute('server',rd,st);r.store()
        wire=json.dumps({'objects':[dict(cpu=1000,mem=1024,name=RUN,vnc_password=SECRET,drives=[],nics=[])]}).encode()
        a=durable.Admission(ACCOUNT,RUN,120,170,SOURCE,wire,90,'b'*64,'c'*64,'caller-create','caller-cleanup',hashlib.sha256(SECRET.encode()).hexdigest())
        with self.cloud() as cloud:
            cap=durable.OfflineLifecycle(cloud,a,clock=lambda:100,lock_root=self.root);r._offline_lifecycle=cap
            self.assertEqual(r.handle_create(),ID);self.assertTrue(r.check_create_complete(ID))
            v=cap.record(r);raw=r.data()[durable.KEY]
            g=cleanup.CleanupGrant(account=ACCOUNT,run=RUN,source=SOURCE,worker=a.worker,preflight=a.preflight,authority=a.authority,cleanup_authority=a.cleanup_authority,window_start=90,create_deadline=120,cleanup_deadline=170,logical=v['logical'],wire=v['wire'],secret_digest=a.secret_digest,binding=v['binding'],journal_digest=hashlib.sha256(raw.encode()).hexdigest(),resource=r.id,stack=st.id)
            c=cleanup.CleanupOnly(cloud,g,lambda:100,self.root);r._offline_lifecycle=c
            self.assertEqual(c.binding,g.binding)
            with self.assertRaises(AttributeError):c.binding='x'
            event=outbox.stage(c,r,'local.test');seen=[]
            result=outbox.deliver(c,r,'local.test',lambda e:seen.append(e) or True)
            self.assertTrue(result['ack']);self.assertFalse(result['live_enabled']);self.assertEqual(event,seen[0]['event_id'])
            self.assertEqual(set(seen[0]),{'version','event_id','obligation','route'})
            self.assertEqual(c.record(r),v);self.assertTrue(c.receipt(r)['escalate'])
            self.assertNotIn(SECRET,json.dumps(seen));self.assertNotIn(ACCOUNT,json.dumps(seen))
            for f in fields(g):
                bad=replace(g,**{f.name:None})
                with self.assertRaises(Refused):cleanup.CleanupOnly(cloud,bad,lambda:100,self.root)
            c.grant=replace(g,authority='changed')
            with self.assertRaises(Refused):outbox.stage(c,r,'local.test')
            c.grant=g
            object.__setattr__(g,'journal_digest','d'*64)
            with self.assertRaises(Refused):_ = c.binding
            object.__setattr__(g,'journal_digest',hashlib.sha256(raw.encode()).hexdigest())
            cloud.trusted_source='e'*64
            with self.assertRaises(Refused):_ = c.binding
            cloud.trusted_source=SOURCE
            self.assertEqual(r.handle_delete(),ID)
            custody=self.root/'continuation.json';continuation.checkpoint(c,r,custody,g)
            entry=registry_adapter.Entry(g,custody,ACCOUNT,SOURCE,{k:props[k] for k in ('username','password','vnc_password')})
            reg=registry_adapter.OfflineRegistry(offline_opt_in=True,entries={(st.id,r.id):entry},cloud=cloud,clock=lambda:100,lock_root=self.root)
            cls=resource_mapping(registry=reg)['CloudSigma::Compute::Instance']
            resumed=cls('server',rd,st);resumed.id=r.id;resumed.resource_id=ID
            reg.restore(resumed)
            self.assertEqual(resumed.handle_delete(),ID)
            self.assertTrue(resumed.check_delete_complete(ID))
            c=resumed._offline_lifecycle
            r=resumed
            self.assertFalse(c.receipt(r)['escalate'])
            with self.assertRaises(Refused):outbox.stage(c,r,'local.test')
            self.assertEqual(cloud.session.adapters[ENDPOINT].calls,['POST','GET','GET','DELETE','GET'])
    def test_boundaries(self):
        with self.assertRaises(TypeError):SDKCloud(FakeHTTP())
        for changes in ({'username':''},{'password':'synthetic'},{'trusted_source':''},{'endpoint':'http://offline.invalid/api/2.0/'},{'offline_opt_in':False}):
            with self.assertRaises(ValueError):self.cloud(**changes)
        with self.assertRaises(ValueError):SDKCloud(requests.adapters.HTTPAdapter(),endpoint=ENDPOINT,username='test',password='test',trusted_source=SOURCE,offline_opt_in=True)
        with self.assertRaises(TypeError):resource_mapping(registry=None)
        reg=registry_adapter.OfflineRegistry(offline_opt_in=True,entries={},cloud=None,clock=lambda:100,lock_root=self.root)
        self.assertTrue(issubclass(resource_mapping(registry=reg)['CloudSigma::Compute::Instance'],plugin.CloudSigmaCompute))
        with self.assertRaises(RuntimeError):plugin.CloudSigmaCompute._legacy_allowed(None)
    def test_installed_origins(self):
        names=['plugin','admission_model','admission_wire','durable','cleanup','continuation','protected_resolver','early_admission','legacy_receipt','outbox','sdk_adapter','registry_adapter','reporting']
        observed={}
        for name in names:
            m=importlib.import_module('cloudsigma_heat.experimental_offline.'+name);p=Path(m.__file__).resolve()
            self.assertIn('site-packages',p.parts);self.assertNotIn('repo',p.parts)
            observed[name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        Path(os.environ['RESULT_IMPORTS']).write_text(json.dumps(observed,indent=2))

if __name__=='__main__':unittest.main(verbosity=2)
