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

    # stop Samba service(s) - in case it's already running
    system("/etc/init.d/samba stop >/dev/null || true")
    system("/etc/init.d/samba-ad-dc stop >/dev/null || true")

    # just in case Samba4 has been set up Samba3 style
    system("/etc/init.d/smbd stop >/dev/null || true")
    system("/etc/init.d/nmbd stop >/dev/null || true")

    remove('/etc/samba/smb.conf')

    system('samba-tool domain provision --realm {REALM} --domain {DOMAIN} --adminpass {ADMIN_PASSWORD} --server-role=dc --use-rfc2307 --option="dns forwarder = 8.8.8.8"'.format(REALM = realm, DOMAIN = domain, ADMIN_PASSWORD = admin_password))

    system('samba-tool user setexpiry {ADMIN_USER} --noexpiry'.format(ADMIN_USER=ADMIN_USER))

    system('samba-tool domain exportkeytab /etc/krb5.keytab')

    system('chown root:root /etc/krb5.keytab; chmod 600 /etc/krb5.keytab')
    
    system('ln -sf /var/lib/samba/private/krb5.conf /etc/krb5.conf')
 
    system('sed -i "s/domain.*/domain {REALM}/" /etc/resolvconf/resolv.conf.d/head'.format(REALM = realm))
    system('sed -i "s/search.*/search {REALM}/" /etc/resolvconf/resolv.conf.d/head'.format(REALM = realm))

    system('service samba-ad-dc start')

    system('sleep 5')

    system('echo {ADMIN_PASSWORD} | kinit {ADMIN_USER}@{REALM}'.format(ADMIN_PASSWORD=admin_password, ADMIN_USER=ADMIN_USER, REALM=realm.upper()))

    system("/etc/init.d/samba-ad-dc restart >/dev/null || true")

if __name__ == "__main__":
    main()

