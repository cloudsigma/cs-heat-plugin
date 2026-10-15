"""Caller-owned in-memory references; not an operational secret store."""
import re
class Refused(RuntimeError): pass
class Resolver:
    def __init__(self, account, values):
        if type(account) is not str or re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',account) is None:
            raise Refused('account schema')
        if type(values) is not dict: raise Refused('resolver schema')
        checked={}
        for alias,value in values.items():
            if type(alias) is not str or re.fullmatch('protected:'+re.escape(account)+r':(username|password|vnc_password):[A-Za-z0-9_-]{1,32}',alias) is None:
                raise Refused('reference schema')
            if type(value) is not str or not 1<=len(value)<=256 or any(ord(c)<32 or ord(c)>126 for c in value):
                raise Refused('secret schema')
            checked[alias]=value
        self.account=account; self._values=checked
    def resolve(self, alias, role, account):
        if type(role) is not str or role not in ('username','password','vnc_password') or account!=self.account:
            raise Refused('reference binding')
        if type(alias) is not str or re.fullmatch('protected:'+re.escape(self.account)+':'+role+r':[A-Za-z0-9_-]{1,32}',alias) is None:
            raise Refused('reference binding')
        if alias not in self._values: raise Refused('reference missing')
        return self._values[alias]
    def close(self): self._values.clear()
