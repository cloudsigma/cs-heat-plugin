"""Offline SDK integration: explicit injected HTTPAdapter required, no default network."""
import json,time,uuid
from urllib.parse import urlsplit
from .admission_model import hex64

def endpoint_url(value):
    if type(value) is not str: raise ValueError("endpoint required")
    u=urlsplit(value)
    if u.scheme!="https" or not u.hostname or u.username or u.password or u.query or u.fragment or not u.path.endswith("/api/2.0/"):
        raise ValueError("endpoint refused")
    return value

import requests
from cloudsigma.generic import GenericClient
class Uncertain(RuntimeError):pass

def canonical(value):
    try:return type(value) is str and str(uuid.UUID(value))==value
    except (ValueError,TypeError,AttributeError):return False

class _Session(requests.Session):
    def resolve_redirects(self,resp,req,**kw):return iter(())

class SDKCloud:
    def __init__(self,adapter,clock=time.time,*,endpoint,username,password,trusted_source,offline_opt_in):
        if offline_opt_in is not True: raise ValueError('offline opt-in required')
        endpoint_url(endpoint)
        if not hex64(trusted_source): raise ValueError('trusted source required')
        if any(type(v) is not str or not v.strip() or v.lower().startswith('synthetic') for v in (username,password)): raise ValueError('explicit authentication required')
        self.trusted_source=trusted_source
        self.endpoint=endpoint
        if not isinstance(adapter,requests.adapters.BaseAdapter) or isinstance(adapter,requests.adapters.HTTPAdapter):raise ValueError('offline adapter required')
        self.clock=clock;self.deadline=0;self._closed=False;self.client=None;self.session=None
        try:
            self.client=GenericClient(api_endpoint=endpoint,username=username,password=password,timeout=1)
            self.session=_Session();self.session.trust_env=False
            for default in self.session.adapters.values(): default.close()
            self.session.adapters.clear();self.session.mount(endpoint,adapter)
        except BaseException:
            self.close();raise
    def close(self):
        if self._closed:return
        self._closed=True
        try:
            if self.session is not None:self.session.close()
        finally:
            if self.client is not None:self.client._session.close()
    def __enter__(self):
        if self._closed:raise Uncertain('closed')
        return self
    def __exit__(self,*args):self.close()
    def check(self):
        if self._closed:raise Uncertain('closed')
        if self.clock()>=self.deadline:raise Uncertain('deadline')
    def call(self,method,path,wire=None):
        self.check()
        left=self.deadline-self.clock()
        if left<=0:raise Uncertain('deadline')
        url=self.client._get_full_url(path);kw=self.client._get_req_args();kw['headers']['Accept-Encoding']='identity'
        req=requests.Request(method,url,data=wire,headers=kw['headers'],auth=kw.get('auth')).prepare()
        try:resp=self.session.send(req,timeout=min(2,left),allow_redirects=False,stream=True,verify=True,proxies={})
        except requests.RequestException:raise Uncertain('transport') from None
        try:
            self.check()
            if resp.url!=url or resp.is_redirect:raise Uncertain('origin or redirect')
            if method=='GET' and resp.status_code==404:
                self.check();return None
            if resp.headers.get('Content-Encoding','identity')!='identity':raise Uncertain('encoding')
            resp.raw.decode_content=False
            try:data=resp.raw.read(262145,decode_content=False)
            except Exception:raise Uncertain('read failed') from None
            self.check()
            if len(data)>262144:raise Uncertain('response cap')
            resp._content=data;resp._content_consumed=True
            expected={'GET':200,'POST':201,'DELETE':204}[method]
            if resp.status_code!=expected:
                try:self.client._process_response(resp)
                except Exception:raise Uncertain('SDK status refusal') from None
                raise Uncertain('status')
            if method=='DELETE':
                self.check();return True
            try:value=self.client._process_response(resp)
            except Exception:raise Uncertain('SDK decode refusal') from None
            if type(value) is not dict:raise Uncertain('shape')
            self.check()
            return value
        finally:resp.close()
    def create_bytes(self,wire):return self.call('POST','/servers/',wire)
    def get(self,id):
        if not canonical(id):raise Uncertain('identifier')
        return self.call('GET','/servers/'+id+'/')
    def delete(self,id):
        if not canonical(id):raise Uncertain('identifier')
        return self.call('DELETE','/servers/'+id+'/')
