cs-heat-plugin
==============

OpenStack Heat plugin for CloudSigma

# Installation

## CloudSigma's Python Library

### Ubuntu

```bash
sudo apt-get -y install python-pip
pip install cloudsigma
```

### CentOS / RHEL

In order to install the CloudSigma module, you first need to install the [EPEL](https://fedoraproject.org/wiki/EPEL) repository, in order to install PIP. The below instructions are for RHEL 6.x / CentOS 6.x. Details for installing the repository, please visit the EPEL site.

```bash
yum install -y wget
wget http://mirrors.servercentral.net/fedora/epel/6/i386/epel-release-6-8.noarch.rpm
rpm -Uvh epel-release-6-8.noarch.rpm
yum install -y python-pip
pip install cloudsigma
```

## Install The Plugin

1. Copy the file into the Heat plugin  directory. For the plugin directiry see the configuration parameter *plugin_dirs* in */etc/heat/heat.conf* on DevStack *plugin_dirs=/usr/lib64/heat,/usr/lib/heat*

2. Restart *heat-api*


## Test the installation

### Test Template

```
{
	"AWSTemplateFormatVersion": "2010-09-09",
	"Description": "CloudSigma test",
	"Parameters": 
	{
		"UserName": 
		{
			"Description": "CloudSigma username",
			"Type": "String"
		},

		"Password": 
		{
			"Description": "CloudSigma password",
			"Type": "String"
		},

		"CloneUUID": 
		{
			"Description": "Drive UUID to clone.",
			"Type": "String"
		}
		
	},

	"Resources": 
	{
		"TestServer": 
		{
			"Type": "CloudSigma::Compute::Instance",
			"Properties": 
			{
				"username": 
				{
					"Ref": "UserName"
				},

				"password": 
				{
					"Ref": "Password"
				},

				"description": "Created by HEAT",
				
				"drive_clone_uuid": 
				{
					"Ref": "CloneUUID"
				},

				"net_ip_uuids": 
				[
					"dhcp"
				]				
			}
		}
	},

	"Outputs": 
	{
		"Server IP": 
		{
			"Value": 
			{
				"Fn::GetAtt": 
				[
					"TestServer",
					"network_ip"
				]
			},

			"Description": "The IP of the server"
		}
	}
}
```

The *CloneUUID* parameter can be taken from the url of the Drive from the Marketplace in the CloudSigma management web app.

By default the datacenter that receives the calls is ZRH, this can be changed by the *api_endpoint* parameter. Use https://_LOC_.cloudsigma.com/api/2.0/ _LOC_ can be one of zrh, lvs, wdc; new locations are added constantly.
 
## Parameters

* api_endpoint
* username
* password
* instance_name
* mem_size
* cpu_mhz
* vnc_password
* meta
* description
* cloudinit_user_data
* ssh_public_key
* drive_clone_uuid
* drive_clone_resize
* drive_uuid
* net_ip_uuids
* net_vlan_uuids
