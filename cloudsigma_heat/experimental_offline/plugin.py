# This is a minimal implementation of the CloudSigma resources
# TODO for a full CS implementation define resources for all API resrources + the attachment points of disks and nics.

import re
import cloudsigma

import time  # to sleep
import json  # to parse the meta so it can be added as an object
import base64  # for cloudinit user-data encoding

from heat.engine import properties, attributes
from heat.engine import resource
from heat.common.i18n import _
from oslo_log import log as logging

logger = logging.getLogger(__name__)

class CloudSigmaCompute(resource.Resource):
    
    @staticmethod
    def _reference_account(props):
        keys=('username','password','vnc_password')
        values=[props.get(k) for k in keys]
        # Exact types before prefix use; stable errors never echo values.
        if any(v is not None and type(v) is not str for v in values):
            raise RuntimeError('Invalid sensitive property type')
        if not any(type(v) is str and v.startswith('protected:') for v in values):
            return None
        account=None
        for role,value in zip(keys,values):
            if type(value) is not str or len(value)>128:
                raise RuntimeError('Protected references required')
            match=re.fullmatch(r'protected:([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}):(username|password|vnc_password):([A-Za-z0-9_-]{1,32})',value)
            if match is None or match.group(2)!=role:
                raise RuntimeError('Invalid protected reference')
            if account is not None and account!=match.group(1):
                raise RuntimeError('Protected account mismatch')
            account=match.group(1)
        return account

    def __init__(self, name, definition, stack):
        props=definition.properties(self.properties_schema,context=stack.context).data
        account=self._reference_account(props)
        if account is not None:
            for key in ('meta','description','cloudinit_user_data','ssh_public_key'):
                if props.get(key):raise RuntimeError('Protected mode extra payload refused')
        super().__init__(name,definition,stack)

    def _protected_properties(self):
        account=self._reference_account({k:self.properties.get(k) for k in ('username','password','vnc_password')})
        cap=getattr(self,'_offline_lifecycle',None)
        if account is None or cap is None or account!=cap.account:
            raise RuntimeError('Protected capability account mismatch')

    def _legacy_allowed(self):
        raise RuntimeError('Legacy transport unavailable in experimental offline package')

    PROPERTIES = (
        API_ENDPOINT, USERNAME, PASSWORD,
        INSTANCE_NAME, MEM_SIZE, CPU_MHZ, VNC_PASSWORD,
        META, DESCRIPTION, CLOUDINIT_USER_DATA, SSH_PUBLIC_KEY,
        DRIVE_CLONE_UUID, DRIVE_CLONE_RESIZE, DRIVE_UUID,
        NET_IP_UUIDS, NET_VLAN_UUIDS
    ) = (
        'api_endpoint', 'username', 'password',
        'instance_name', 'mem_size', 'cpu_mhz', 'vnc_password',
        'meta', 'description', 'cloudinit_user_data', 'ssh_public_key',
        'drive_clone_uuid', 'drive_clone_resize', 'drive_uuid',
        'net_ip_uuids', 'net_vlan_uuids'
    )

    properties_schema = {
    
        #------------------API--------------------------------
        API_ENDPOINT: properties.Schema(
            properties.Schema.STRING,
            _('The URL for the RESTful API. Explicit offline endpoint required.'),
            required=True
        ),

        USERNAME: properties.Schema(
            properties.Schema.STRING,
            _('The username in the CloudSigma Cloud.'),
            required=True            
        ),

        PASSWORD: properties.Schema(
            properties.Schema.STRING,
            _('The password in the CloudSigma Cloud.'),
            required=True
        ),
        #------------------API--------------------------------
                         
        INSTANCE_NAME: properties.Schema(
            properties.Schema.STRING,
            _('The instance name. The default is "Server <random uuid>".'),
            required=False,
            default=''
        ),
        MEM_SIZE: properties.Schema(
            properties.Schema.INTEGER,
            _('Memory size in MB. The default is 256MB'),
            required=False,
            default=256
        ),
        CPU_MHZ: properties.Schema(
            properties.Schema.INTEGER,
            _('CPU speed in MHz. The default is 250MHz'),
            required=False,
            default=250
        ),
        VNC_PASSWORD: properties.Schema(
            properties.Schema.STRING,
            _('The VNC password for remote screen. The default is Cl0ud_Sigma'),
            required=True,
            default='Cl0ud_Sigma'
        ),

        
        #------------------DRIVES--------------------------------
        # FIXME works with a single drive for the minimal implementation
        DRIVE_CLONE_UUID: properties.Schema(
            properties.Schema.STRING,
            _('Drive UUID to clone and attach'),
            required=False            
        ),

        DRIVE_CLONE_RESIZE: properties.Schema(
            properties.Schema.INTEGER,
            _('Resize the cloned drive. Size in bytes. The default 4GB'),
            required=False            
        ),

        DRIVE_UUID: properties.Schema(
            properties.Schema.STRING,
            _('Drive UUID to attach'),
            required=False            
        ),
        #------------------DRIVES--------------------------------
                         
                
        #------------------METADATA--------------------------------                  
        META: properties.Schema(
            properties.Schema.STRING,
            _('The metadata to pass to the server. It needs to be a proper JSON'),
            required=False,
            default='{}'
        ),
        DESCRIPTION: properties.Schema(
            properties.Schema.STRING,
            _('The instance\'s description'),
            required=False            
        ),
        CLOUDINIT_USER_DATA: properties.Schema(
            properties.Schema.STRING,
            _('Cloudinit user data. Requires cloudinit > 0.7.5.'),
            required=False
        ),
        SSH_PUBLIC_KEY: properties.Schema(
            properties.Schema.STRING,
            _('SSH public key for the default user. Requires cloudinit > 0.7.5.'),
            required=False
        ),
        #------------------METADATA--------------------------------
        
        #------------------NETWORKING--------------------------------
        # FIXME for a minimal implementation - accept here also dhcp and manual 
        NET_IP_UUIDS: properties.Schema(
            properties.Schema.LIST,
            _('The subscribed IP UUID. Can be also "dhcp" or "manual"'),
            required=False,
            # XXX http://docs.openstack.org/developer/heat/pluginguide.html says that 
            # Based on the property type, properties without a set value will return the default 'empty' value for LIST is [] 
            # but we get 'NoneType' object is not iterable
            default=[] 
        ),
        NET_VLAN_UUIDS: properties.Schema(
            properties.Schema.LIST,
            _('The subscribed VLAN UUIDs.'),
            required=False,
            # XXX http://docs.openstack.org/developer/heat/pluginguide.html says that 
            # Based on the property type, properties without a set value will return the default 'empty' value for LIST is [] 
            # but we get 'NoneType' object is not iterable
            default=[]
        )
        #------------------NETWORKING--------------------------------
    }

    attributes_schema = {        
        'network_ip': attributes.Schema(_('Container ip addresses'), type=attributes.Schema.LIST)        
    }

    # -------------------------------- RESOURCE MANAGERS -----------------------------------------------------
    # TODO in a more detailed implementation, create a different resource for each of these managers
    def _get_compute_manager(self):
        self._legacy_allowed()
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        return cloudsigma.resource.Server(
                api_endpoint=endpoint,
                username=username,
                password=password
            )

    def _get_drive_manager(self):
        self._legacy_allowed()
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        return cloudsigma.resource.Drive(
            api_endpoint=endpoint,
            username=username,
            password=password
        )
    
    def _get_ip_manager(self):
        self._legacy_allowed()
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        return cloudsigma.resource.IP(
            api_endpoint=endpoint,
            username=username,
            password=password
        )
        
    def _get_vlan_manager(self):
        self._legacy_allowed()
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        return cloudsigma.resource.VLAN(
            api_endpoint=endpoint,
            username=username,
            password=password
        )
    
    def _get_compute_data(self, compute_id):
        return self._get_compute_manager().get(compute_id)        
    # -------------------------------- RESOURCE MANAGERS -----------------------------------------------------
                    

    def _resolve_attribute(self, name):
        if not self.resource_id:
            return
        if name == 'network_ip':
            _instance_data = self._get_compute_data(self.resource_id)
            res = []
            for nic in _instance_data.get('nics', []):
                runtime = nic.get('runtime') or {}
                ipv4 = runtime.get('ip_v4') or {}
                address = ipv4.get('uuid')
                if isinstance(address, str):
                    res.append(address)
            return res

    def handle_create(self):
        cap = getattr(self, '_offline_lifecycle', None)
        if cap is None: raise RuntimeError('Creation disabled: operational admission missing')
        self._protected_properties()
        return cap.create(self)

    def _wait_for_status(self, manager, resource_id, expected, deadline,
                         max_polls=12, cancelled=lambda: False, sleep=time.sleep):
        if not resource_id or max_polls < 1 or max_polls > 12:
            raise ValueError('Invalid polling bound')
        for attempt in range(max_polls):
            if cancelled() or time.monotonic() >= deadline:
                raise RuntimeError('Polling cancelled or expired')
            value = manager.get(resource_id)
            if cancelled() or time.monotonic() >= deadline:
                raise RuntimeError('Polling cancelled or expired')
            if not isinstance(value, dict) or not isinstance(value.get('status'), str):
                raise ValueError('Malformed resource status')
            if value['status'] == expected:
                return value
            if attempt + 1 < max_polls:
                sleep(min(1, max(0, deadline - time.monotonic())))
        raise RuntimeError('Polling exhausted')

    # TODO migrate the drive creation here
    def check_delete_complete(self, cookie):
        cap = getattr(self, '_offline_lifecycle', None)
        if cap is None: raise RuntimeError('Cleanup reconciliation disabled')
        self._protected_properties()
        return cap.reconcile(self)

    def check_create_complete(self, _compute_id):
        cap = getattr(self, '_offline_lifecycle', None)
        if cap is not None:
            self._protected_properties()
            return cap.complete(self)
        _instance_data = self._get_compute_data(_compute_id)
        return _instance_data['status'] == 'running'

    def handle_suspend(self):
        if getattr(self, '_offline_lifecycle', None) is not None: raise RuntimeError('Offline fixture power actions disabled')
        if not self.resource_id:
            return
        self._get_compute_manager().stop(self.resource_id)
        return self.resource_id

    def check_suspend_complete(self, _compute_id):
        if getattr(self, '_offline_lifecycle', None) is not None: raise RuntimeError('Offline fixture power actions disabled')
        _instance_data = self._get_compute_data(_compute_id)
        return _instance_data['status'] == 'stopped'

    def handle_resume(self):
        if getattr(self, '_offline_lifecycle', None) is not None: raise RuntimeError('Offline fixture power actions disabled')
        if not self.resource_id:
            return
        self._get_compute_manager().start(self.resource_id)
        return self.resource_id

    def check_resume_complete(self, _compute_id):
        if getattr(self, '_offline_lifecycle', None) is not None: raise RuntimeError('Offline fixture power actions disabled')
        _instance_data = self._get_compute_data(_compute_id)
        return _instance_data['status'] == 'running'

    def handle_delete(self):
        cap = getattr(self, '_offline_lifecycle', None)
        if cap is not None:
            self._protected_properties()
            return cap.delete(self)
        if self.resource_id is None:
            return
        # A Heat resource_id alone does not prove ownership of attached disks.
        # Preserve obligations; never cascade-delete adopted or ambiguous resources.
        raise RuntimeError('Deletion disabled: durable ownership proof required')

def resource_mapping():
    return {
        'CloudSigma::Compute::Instance': CloudSigmaCompute
    }
