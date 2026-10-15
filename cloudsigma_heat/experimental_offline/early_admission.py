"""Offline protected-template entry. Not a global Heat API interceptor."""
import json
import re
from heat.engine import template
from .sdk_adapter import endpoint_url

class Refused(RuntimeError):
    pass

def admit(raw, account, *, endpoint):
    endpoint_url(endpoint)
    # Immutable wire input and a bounded, plain reference-only subset prevent
    # intrinsic functions/parameter defaults from concealing literal secrets.
    if type(raw) is not bytes or len(raw) > 65536:
        raise Refused('template schema')
    if type(account) is not str or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', account):
        raise Refused('account schema')
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise Refused('template schema')
            out[k] = v
        return out
    try:
        doc = json.loads(raw, object_pairs_hook=pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(Refused('template schema')))
    except Exception:
        invalid = True
    else:
        invalid = False
    # Raise outside the handler: suppressing display with `from None` alone
    # leaves JSONDecodeError.doc reachable through __context__.
    if invalid:
        raise Refused('template schema')
    if type(doc) is not dict or set(doc) != {'heat_template_version', 'resources'}:
        raise Refused('template schema')
    if doc['heat_template_version'] != '2018-08-31' or type(doc['resources']) is not dict or set(doc['resources']) != {'server'}:
        raise Refused('template schema')
    resource = doc['resources']['server']
    if type(resource) is not dict or set(resource) != {'type', 'properties'} or resource['type'] != 'CloudSigma::Compute::Instance':
        raise Refused('template schema')
    props = resource['properties']
    if type(props) is not dict or set(props) != {'username', 'password', 'vnc_password', 'api_endpoint'} or props['api_endpoint'] != endpoint:
        raise Refused('template schema')
    for role in ('username', 'password', 'vnc_password'):
        value = props[role]
        if type(value) is not str or re.fullmatch('protected:' + re.escape(account) + ':' + role + r':[A-Za-z0-9_-]{1,32}', value) is None:
            raise Refused('protected reference')
    return template.Template(doc)

def store(raw, account, context, *, endpoint):
    # Admission finishes before Template construction/store. No caller callback
    # or mutation opportunity exists between validation and persistence.
    return admit(raw, account, endpoint=endpoint).store(context)
