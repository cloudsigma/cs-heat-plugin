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

TODO
