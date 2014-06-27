# This is a minimal implementation of the CloudSigma resources
# TODO for a full CS implementation define resources for all API resrources + the attachment points of disks and nics.

import cloudsigma

import time  # to sleep
import json  # to parse the meta so it can be added as an object
import base64  # for cloudinit user-data encoding

from heat.engine import properties
from heat.engine import resource
from heat.openstack.common.gettextutils import _
from heat.openstack.common import log as logging

logger = logging.getLogger(__name__)

class CloudSigmaCompute(resource.Resource):
    
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
            _('The URL for the RESTful API. Defaults to https://zrh.cloudsigma.com/api/2.0/'),
            required=True,
            default='https://zrh.cloudsigma.com/api/2.0/'
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
        'network_ip': _('Container ip address')        
    }

    def __int__(self, name, json_snippet, stack):
        super(CloudSigmaCompute, self).__init__(name, json_snippet, stack)

    # -------------------------------- RESOURCE MANAGERS -----------------------------------------------------
    # TODO in a more detailed implementation, create a different resource for each of these managers
    def _get_compute_manager(self):
    	endpoint = self.properties.get(self.API_ENDPOINT)
    	username = self.properties.get(self.USERNAME)
    	password = self.properties.get(self.PASSWORD)
    	logger.debug(_("_get_compute_manager api_endpoint=%s, username=%s") % (endpoint, username))
        return cloudsigma.resource.Server(
                api_endpoint=endpoint,
                username=username,
                password=password
            )

    def _get_drive_manager(self):
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        logger.debug(_("_get_drive_manager api_endpoint=%s, username=%s") % (endpoint, username))
        return cloudsigma.resource.Drive(
            api_endpoint=endpoint,
            username=username,
            password=password
        )
    
    def _get_ip_manager(self):
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        logger.debug(_("_get_ip_manager api_endpoint=%s, username=%s") % (endpoint, username))
        return cloudsigma.resource.IP(
            api_endpoint=endpoint,
            username=username,
            password=password
        )
        
    def _get_vlan_manager(self):
        endpoint = self.properties.get(self.API_ENDPOINT)
        username = self.properties.get(self.USERNAME)
        password = self.properties.get(self.PASSWORD)
        logger.debug(_("_get_ip_manager api_endpoint=%s, username=%s") % (endpoint, username))
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
            for nic in _instance_data['nics']:
                if nic['runtime']:
                    try:
                        res.append(nic['runtime']['ip_v4']['uuid'])
                    except TypeError:
                        pass
            return res

    def handle_create(self):
        # create the resource managers
        _drive_manager = self._get_drive_manager()
        logger.debug(_("list drives %s") % _drive_manager.list())

        _compute_manager = self._get_compute_manager()
        logger.debug(_("list servers %s") % _compute_manager.list())


        # handle meta
        _meta = json.loads(self.properties.get(self.META))
        if self.properties.get(self.DESCRIPTION):
            _meta['description'] = self.properties.get(self.DESCRIPTION)
        # FIXME it overwrites the field that may be in meta
        if self.properties.get(self.SSH_PUBLIC_KEY):
            _meta['ssh_public_key'] = self.properties.get(self.SSH_PUBLIC_KEY)
        # FIXME base64 encode - overwrites base64_fields, cloudinit_user_data
        if self.properties.get(self.CLOUDINIT_USER_DATA):
            _meta['base64_fields'] = 'cloudinit-user-data'  #XXX hyphens not underscores!!! 
            _meta['cloudinit-user-data'] = base64.b64encode(self.properties.get(self.CLOUDINIT_USER_DATA))            

        # create the server description
        _compute_description = {
            'name': self.properties.get(self.INSTANCE_NAME),
            'cpu': self.properties.get(self.CPU_MHZ),
            'mem': self.properties.get(self.MEM_SIZE) * 1024 ** 2,
            'vnc_password': self.properties.get(self.VNC_PASSWORD),
            'drives': [],
            'nics':[],
            # we need to parse the JSON format supplied as a parameter to add it as an object - not as a string
            'meta': _meta
        }        
        
        #--------------------------HANDLE DRIVES --------------------------------------
        # FIXME drives can be left behind after an unsuccessful create
        
        # decide what to do with the drives
        if self.properties.get(self.DRIVE_UUID):
            # so we have a drive
            
            # check the drive with GET 
            _drive = _drive_manager.get(self.properties.get(self.DRIVE_UUID))
            
            # add the drive to the server description
            # TODO do append instead of setting the drives list - this requires computing the dev_channel attachment point            
            _compute_description['drives'].append({
                 'boot_order': 1,
                 'dev_channel': "0:0",
                 'device': "virtio",
                 'drive': {'uuid':_drive['uuid']}
            })
                    
        elif self.properties.get(self.DRIVE_CLONE_UUID):
            # we need to clone a drive - its an asynchronous operation
            
            # check the drive - will raise an exception if uuid is wrong 
            # cloudsigma.errors.ClientError: (404, u'[{"error_point": null, 
            # "error_type": "notexist", "error_message": "Object with uuid b49dc74a-f7a5-42f5-9842-290e7475d67a does not exist"}]')
            _drive = _drive_manager.get(self.properties.get(self.DRIVE_CLONE_UUID))
                                    
            # clone the drive
            # will raise exception if is mounted, etc.
            _clone = _drive_manager.clone(_drive['uuid'])
            
            # check the clone
            while True:  # wait loop for the clone creation to finish
                if _drive_manager.get(_clone['uuid'])['status'] == 'unmounted':  # FIXME is the test right
                    break
                else:
                    time.sleep(5);  # FIXME do we need this, do we need a hard timeout
            
            if self.properties.get(self.DRIVE_CLONE_RESIZE):
                # we need to resize the drive
                _clone['size'] = self.properties.get(self.DRIVE_CLONE_RESIZE)  # TODO sanity check the clone new size 
                _drive_manager.resize(_clone['uuid'], _clone)
                
                # check the clone
                while True:  # wait loop for the clone creation to finish
                    if _drive_manager.get(_clone['uuid'])['status'] == 'unmounted':  # FIXME is the test right
                        break
                    else:
                        time.sleep(5);  # FIXME do we need this, do we need a hard timeout                

            # attach the drive by changing the configuration
            # TODO do append instead of setting the drives list - this requires computing the dev_channel
            _compute_description['drives'].append({
                 'boot_order': 1,
                 'dev_channel': "0:0",
                 'device': "virtio",
                 'drive': {'uuid':_clone['uuid']}
            })
        #--------------------------HANDLE DRIVES --------------------------------------

        #--------------------------HANDLE NETWORK --------------------------------------
        for _ip in self.properties.get(self.NET_IP_UUIDS):
            # handle the public IPs
            
            _ip_manager = self._get_ip_manager()
            logger.debug(_("list IPs %s") % _ip_manager.list())
            
            # handle the different types of configuration
            if _ip == 'dhcp':
                _ip_attachment = {'ip_v4_conf': {'conf': 'dhcp'}}
            elif _ip == 'manual':
                _ip_attachment = {'ip_v4_conf': {'conf': 'manual'}}
            else:
                # check the uuid with GET
                _ip_manager.get(_ip)
                
                _ip_attachment = {'ip_v4_conf': {'conf': 'static', 'ip': _ip}}
            
            # attach the ip
            _compute_description['nics'].append(_ip_attachment)
            
        for _vlan in self.properties.get(self.NET_VLAN_UUIDS):
            # handle the private networks            
            _vlan_manager = self._get_vlan_manager()
            
            # check VLAN uuid with GET
            _vlan_manager.get(_vlan)
            
            _vlan_attachment = {'vlan': _vlan}
            _compute_description['nics'].append(_vlan_attachment)
            
        #--------------------------HANDLE NETWORK --------------------------------------

                    
        # create the server with the attached drives and nics
        logger.debug(_("Trying to create a VM with this description %s") % _compute_description)
        _compute = _compute_manager.create(_compute_description)
        logger.debug(_("VM Created %s") % _compute)
        
        # save the uuid for future operations
        self.resource_id_set(_compute['uuid'])
        
        # start the sever
        _compute_manager.start(_compute['uuid'])

        # use this object to check for node creation completion
        return _compute['uuid']

    # TODO migrate the drive creation here
    def check_create_complete(self, _compute_id):
        logger.debug(_("Check create server %s") % self.resource_id)
        _instance_data = self._get_compute_data(_compute_id)
        return _instance_data['status'] == 'running'

    def handle_suspend(self):
        if not self.resource_id:
            return
        self._get_compute_manager().stop(self.resource_id)
        return self.resource_id

    def check_suspend_complete(self, _compute_id):
        _instance_data = self._get_compute_data(_compute_id)
        return _instance_data['status'] == 'stopped'

    def handle_resume(self):
        if not self.resource_id:
            return
        self._get_compute_manager().start(self.resource_id)
        return self.resource_id

    def check_resume_complete(self, _compute_id):
        _instance_data = self._get_compute_data(_compute_id)
        return _instance_data['status'] == 'running'

    def handle_delete(self):
        logger.debug(_("Delete server %s") % self.resource_id)

        # enables to delete a stack if it was not created successfully, e.a. no resource_id
        if self.resource_id is None:
            logger.debug(_("Delete: resource_id is empty - nothing to do, exitting."))
            return
         
        _compute_manager = self._get_compute_manager()
        
        # try to get the server description
        try:
            _instance_data = self._get_compute_data(self.resource_id)
        except cloudsigma.errors.ClientError:
            # throws an 404 nonexistent - nothing to delete
            return
                
        if _instance_data['status'] == 'running':
            logger.debug(_("Delete server %s; stopping first ...") % self.resource_id)
            _compute_manager.stop(self.resource_id)
            time.sleep(5)  # XXX wait for the status to update       
            while self._get_compute_data(self.resource_id)['status'] == 'stopping': 
                # XXX May happen that the status is still = 'running'
                # XXX introduce a hard timeout
                logger.debug(_("Delete server %s; waiting to be stopped; sleep 5 secs") % self.resource_id)
                time.sleep(5)  # FIXME wait a little so not to flood the server
       
        _compute_manager.delete_with_disks(self.resource_id)

def resource_mapping():
    return {
        'CloudSigma::Compute::Instance': CloudSigmaCompute
    }
