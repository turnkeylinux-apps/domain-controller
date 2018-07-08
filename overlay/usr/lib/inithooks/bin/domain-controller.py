#!/usr/bin/python
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org> - all rights reserved
"""Configure samba domain and password

Options:
    --pass=      if not provided, will ask interactively
    --realm=     if not provided, will ask interactively
                 DEFAULT=domain.lan
    --domain=    if not provided, will ask interactively
                 DEFAULT=DOMAIN
    --join=      [true|false]
                 if not provided, will ask interactively
                 DEFAULT=false
    --join_ns=   if not provided, will ask interactively
                 only required if --join=true; otherwise
                 ignored
    --join_check=[true|false]
                 only required if --join=true; otherwise
                 ignored
                 DEFAULT=true                 
"""

import sys
import getopt
import subprocess
import socket

from subprocess import PIPE
from os import remove
from os import path
from string import digits, ascii_uppercase, ascii_lowercase, punctuation

from executil import system, getoutput
from dialog_wrapper import Dialog

def usage(s=None):
    if s:
        print >> sys.stderr, "Error:", s
    print >> sys.stderr, "Syntax: %s [options]" % sys.argv[0]
    print >> sys.stderr, __doc__
    sys.exit(1)

def fatal(s):
    print >> sys.stderr, "Error:", s
    sys.exit(1)

def valid_ip(address):
    try: 
        socket.inet_aton(address)
        return True
    except:
        return False

ADMIN_USER="administrator"

DEFAULT_DOMAIN="DOMAIN"
DEFAULT_REALM="domain.lan"

HOSTNAME=getoutput('hostname -s').strip()
NET_IP=getoutput('hostname -I').strip()

NET_IP321=NET_IP.split('.')[:-1]
NET_IP321.reverse()
NET_IP321='.'.join(NET_IP321)
NET_IP4=NET_IP.split('.')[-1]

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help', 'pass=', 'realm=', 'domain=', 'join=', 'join_ns=', 'join_check='])
    except getopt.GetoptError, e:
        usage(e)

    realm = ""
    domain = ""
    admin_password = ""

    join = "ask interactively"
    join_nameserver = False
    join_check = True

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt == '--pass':
            admin_password = val
        elif opt == '--realm':
            realm = val
            DEFAULT_DOMAIN = realm.split('.')[0].upper()
        elif opt == '--domain':
            domain = val
        elif opt == '--join':
            if(val):
                join = (val in ['true', 'True'])
        elif opt == '--join_ns':
            join_nameserver = val
        elif opt == '--join_check':
            if(val):
                join_check = (val in ['true', 'True'])

    while 1:

        if join == "ask interactively":
            d = Dialog('Turnkey Linux - First boot configuration')
            join = d.yesno(
                "Join existing AD?",
                "You can create the Active Directory or join existing.",
                "Join",
                "Create")            

        if not realm:
            d = Dialog('Turnkey Linux - First boot configuration')
            realm = d.get_input(
                "Samba/Kerberos Realm",
                "Enter realm you would like to use.",
                DEFAULT_REALM)
            DEFAULT_DOMAIN = realm.split('.')[0].upper()    

        if not domain:
            d = Dialog('TurnKey Linux - First boot configuration')
            domain = d.get_input(
                "Samba Domain",
                "Enter domain you would like to use.",
                DEFAULT_DOMAIN)    

        if not admin_password:
            if 'd' not in locals():
                d = Dialog('TurnKey Linux - First boot configuration')    

            admin_password = d.get_password(
                    "Samba Password",
                    "Enter password for the samba 'administrator' account.",
                    pass_req=8, min_complexity=3)    

        if join and not join_nameserver:
            d = Dialog('Turnkey Linux - First boot configuration')
            while 1:
                retcode, join_nameserver = d.inputbox(
                    "Add nameserver",
                    "Set the DNS server IP and AD DNS domain in your /etc/resolv.conf.",
                    "",
                    "Add",
                    "Skip")    

                if retcode == 1:
                    join_nameserver = ""
                    break    

                if not valid_ip(join_nameserver):
                    d.error('IP is not valid.')
                    continue    

                if d.yesno("Is your DNS correct?", join_nameserver):
                    break    

        if join:            
            system('/usr/lib/inithooks/bin/sambaconf_join.sh -r {REALM} -d {DOMAIN} -u {ADMIN_USER} -p {ADMIN_PASSWORD} -n {NAME_SERVER} 2> /var/log/dc.log || true'.format(DOMAIN = domain, ADMIN_PASSWORD=admin_password, ADMIN_USER=ADMIN_USER, REALM=realm, NAME_SERVER=join_nameserver))
            if  'ERROR' in open('/var/log/dc.log').read():                
                if not join_check:
                    break                    
                system('mv /var/log/dc.log /var/log/dc.log_old')
                d = Dialog('Turnkey Linux - First boot configuration')
                d.error("Can't join a Samba DC to an Existing Active Directory.\nPlease check your input.")
                realm = ""
                domain = ""
                admin_password = ""
                join = False
                join_nameserver = False
                continue


        else:    
            system('/usr/lib/inithooks/bin/sambaconf_add.sh -r {REALM} -d {DOMAIN} -u {ADMIN_USER} -p {ADMIN_PASSWORD} '.format(DOMAIN = domain, ADMIN_PASSWORD=admin_password, ADMIN_USER=ADMIN_USER, REALM=realm))
        break

if __name__ == "__main__":
    main()
