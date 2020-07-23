#!/usr/bin/python3
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org> - all rights reserved
# Copyright (c) 2011-2020 TurnKey GNU/Linux <admin@turnkeylinux.org>
"""Configure Samba AD domain, realim and administrator password

Options:
    --pass=         AD domain 'Administrator' password.
                    Must not contain '(' or ')' characters.
                    If not provided, will ask interactively.
    --realm=        AD Kerberos realm & AD DNS zone to create or join.
                    Realm will be uppercase and DNS zone will be lower case.
                    If not set will ask interactively.
                    DEFAULT=DOMAIN.LAN
    --domain=       NetBIOS domain (aka 'workgroup') to create or join.
                    If Realm and Domain are not set, will ask interactively.
                    If Realm set non-interactively, domain will be the first
                    part of the domain, before the first dot/period.
                    DEFAULT=DOMAIN
   --join_ns=       To join an existing domain, you must provide the IPv4 of
                    nameserver to use (plus the other 3 options).
                    If '--pass', '--realm' & '--domain' set, but not
                    '--join_ns", this script will create a new domain. If
                    '--pass' &/or '--realm' &/or '--domain' not set, will ask
                    interactively.
                    If '--join_ns' is set but is not a valid IPv4, will ask
                    interactively.

Environment::

    _TURNKEY_INIT   If set, will assume the script is running under
                    'turnkey-init' and will run interactively. An initial
                    confirmation re reconfiguration will also be asked.

Notes:
------

Warning: previous configuration will be cleared!

To create a new AD domain non-interactively, set valid '--pass', '--realm' and
'--domain'.

To join an existing domain non-interactively, set valid '--pass', '--realm',
--domain' and '--join_ns'.

To run interactively, ensure that '--pass' &/or '--realm' &/or '--domain' are
_not_ set. Or set env var '_TURNKEY_INIT'. All components that are not provided
valid values via commandline will be asked.
"""

import sys
import os
import glob
import getopt
import socket
import subprocess
from subprocess import PIPE, STDOUT
from string import digits, ascii_uppercase, ascii_lowercase, punctuation

from dialog_wrapper import Dialog


ADMIN_USER = "administrator"
DEFAULT_REALM = "DOMAIN.LAN"
DEFAULT_DOMAIN = "DOMAIN"
TURNKEY_INIT = os.getenv("_TURNKEY_INIT")


def getoutput(command):
    return subprocess.run(command,
                          encoding='utf-8',
                          stdout=PIPE).stdout.strip()


HOSTNAME = getoutput(['hostname', '-s'])
NET_IP = getoutput(['hostname', '-I'])

NET_IP321 = NET_IP.split('.')[:-1]
NET_IP321.reverse()
NET_IP321 = '.'.join(NET_IP321)
NET_IP4 = NET_IP.split('.')[-1]


def usage(s=None):
    if s:
        print("Error:", s, file=sys.stderr)
    print("Syntax: %s [options]" % sys.argv[0], file=sys.stderr)
    print(__doc__, file=sys.stderr)
    sys.exit(1)


def fatal(s):
    print("Error:", s, file=sys.stderr)
    sys.exit(1)


def valid_ip(address):
    try:
        socket.inet_aton(address)
        return address
    except OSError:
        return False


def valiadate_realm(realm):
    realm = realm.strip('.')
    if len(realm) > 255:
        return None
    for bit in realm.split(','):
        if len(bit) < 0 or len(bit) > 63:
            return None
        if not bit.isalpha():
            return None
    return realm.upper()


def valiadate_netbios(domain):
    if len(domain) < 1 or len(domain) > 15:
        return None
    if not domain.isalpha():
        return None
    return domain.upper()


def rm_f(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def rm_glob(path):
    file_list = glob.glob(path)
    for file_path in file_list:
        rm_f(file_path)


def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help',
                                        'pass=',
                                        'domain='
                                        'realm=',
                                        'join_ns='])
    except getopt.GetoptError as e:
        usage(e)

    interactive = False
    domain = ""
    realm = ""
    admin_password = ""
    join_nameserver = ""
    join = ""

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt == '--pass':
            admin_password = val
        elif opt == '--realm':
            realm = validate_realm(val)
        elif opt == '--domain':
            domain = validate_domain(val)
        elif opt == '--join_ns':
            join_nameserver = val

    if (
            (not (realm and domain and admin_pass)) or
            (join_nameserver and not valid_ip(join_nameserver)) or
            TURNKEY_INIT):
        interactive = True
    elif realm and domain and admin_pass and join_nameserver:
        join_nameserver = valid_ip(join_nameserver)

    while True:
        if TURNKEY_INIT:
            d = Dialog('Turnkey Linux - First boot configuration')
            do_it = d.yesno("Reconfigure Samba?",
                            "Existing Samba config will be removed.\n\n"
                            "Cancelling will leave existing config in place.\n"
                            "\nContinue?", "Reconfigure", "Cancel")
            if not do_it:
                sys.exit(0)

        if interactive and not join_nameserver:
            d = Dialog('Turnkey Linux - First boot configuration')
            create = d.yesno(
                "Create new AD or join existing?",
                "You can create a new Active Directory or join an existing one.",
                "Create",
                "Join")
            if not create:
                join = "join"

        if not realm:
            d = Dialog('Turnkey Linux - First boot configuration')
            realm = d.get_input(
                "Samba Kerberos Realm / AD DNS zone",
                "Kerberos Realm should be 2 or more groups of 63 or less"
                " ASCII characters, separated by dot(s). Kerberos realm"
                " will be stored as uppercase; DNS zone as"
                " lowercase\n\n"
                "Enter the Realm / DNS zone you would like to use.",
                DEFAULT_REALM)

        if not domain:
            d = Dialog('TurnKey Linux - First boot configuration')
            domain = d.get_input(
                "Samba NetBIOS Domain (aka workgroup)",
                "The NetBIOS domain (aka workgroup) should be 15 or less ASCII"
                " characters.\n\n"
                "Enter the NetBIOS domain (workgroup) you would like to use.",
                DEFAULT_DOMAIN)
            domain = domain.lower()

        if not admin_password:
            d = Dialog('TurnKey Linux - First boot configuration')
            admin_password = d.get_password(
                    "Samba Password",
                    "Enter password for the samba 'Administrator' account.",
                    pass_req=8, min_complexity=3, blacklist=['(', ')'])

        if interactive and join == 'join':
            d = Dialog('Turnkey Linux - First boot configuration')
            while True:
                join_nameserver = d.inputbox(
                    "Add nameserver",
                    "Set the DNS server IP for your existing AD domain DNS server",
                    join_nameserver,
                    "Add")

                if not valid_ip(join_nameserver):
                    d.error('IP is not valid.')
                    continue

        # Stop any Samba services
        services = ['samba', 'samba-ad-dc', 'smbd', 'nmbd']
        for service in services:
            subprocess.run(['systemctl', 'stop', service], stderr=PIPE)
        # Remove Samba & Kerberos conf
        rm_f('/etc/samba/smb.conf')
        rm_f('/etc/krb5.conf')
        # Remove Samab DBs
        dirs = ['/var/run/samba', '/var/lib/samba',
                '/var/cache/samba', '/var/lib/samba/private']
        for _dir in dirs:
            for _db_file in ['*.tdb', '*.ldb']:
                rm_glob('/'.join([_dir, _db_file]))

        if join_nameserver:
            samba_domain = ['samba-tool', 'domain', 'join',
                            realm, 'DC',
                            '-U"{}\\Administrator"'.format(domain),
                            '--password={}'.fomat(password),
                            "--option='idmap_ldb:use rfc2307 = yes'"]
        else:
            samba_domain = ['samba-tool', 'domain', 'provision',
                            '--server-role=dc', '--use-rfc2307',
                            '--dns-backend=SAMBA_INTERNAL',
                            '--realm={}'.format(realm),
                            '--domain={}'.format(domain),
                            '--adminpass={}'.format(admin_password)]
#                            '--option="dns forwarder = 8.8.8.8"']

        while True:
            samba_run = subprocess.Popen(samba_domain, encoding='utf-8',
                                         stdout=PIPE, stderr=STDOUT)
            while True:
                out = samba_run.stdout.read(1)
                if out == '' and samba_run.poll() != None:
                    break
                if out != '':
                    sys.stdout.write(out)
                    sys.stdout.flush()

            if create:
                conf_file = '/var/samba/smb.conf'
                # add DNS forwarder here....

            if samba_run.returncode != 0:
                if interactive:
                    d = Dialog('Turnkey Linux - First boot configuration')
                    retry = d.error("{}\n\n".format(samba_run.stderr))
                else:
                    print("Errors in processing domain-controller inithook data.")
                    sys.exit(1)


if __name__ == "__main__":
    main()
