#!/usr/bin/python
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org> - all rights reserved
"""Configure samba domain and password

Options:
    --pass=      if not provided, will ask interactively
    --realm=     if not provided, will ask interactively
                 DEFAULT=domain.lan
    --domain=    if not provided, will ask interactively
                 DEFAULT=DOMAIN
"""

import sys
import getopt
import subprocess
from subprocess import PIPE
from os import remove
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
                                       ['help', 'pass=', 'realm=', 'domain='])
    except getopt.GetoptError, e:
        usage(e)

    realm = ""
    domain = ""
    admin_password = ""
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
                "Enter new password for the samba 'administrator' account.",
                pass_req=8, min_complexity=3)

    
    system('/usr/lib/inithooks/bin/sambaconf.sh -r {REALM} -d {DOMAIN} -u {ADMIN_USER} -p {ADMIN_PASSWORD}'.format(DOMAIN = domain, ADMIN_PASSWORD=admin_password, ADMIN_USER=ADMIN_USER, REALM=realm))

if __name__ == "__main__":
    main()
