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
import shutil
import getopt
import socket
import time
import subprocess
from subprocess import PIPE, STDOUT
from string import digits, ascii_uppercase, ascii_lowercase, punctuation

from dialog_wrapper import Dialog


ADMIN_USER = "administrator"
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


def error_msg(msg, interactive):
    if interactive:
        return False, msg
    else:
        fatal(msg)


def valid_ip(address):
    try:
        socket.inet_aton(address)
        return address
    except OSError:
        return False


def validate_realm(realm, interactive):
    err = []
    realm = realm.strip('.')
    if len(realm) > 255:
        err = error_msg("Realm must be less than 255 characters.", interactive)
    for bit in realm.split('.'):
        if len(bit) < 0 or len(bit) > 63:
            err = error_msg("All realm segments must be greater than 0 and"
                            " less than 63 characters.",
                            interactive)
        if not bit.isalnum():
            err = error_msg("All realm segment characters must be"
                            " alphanumeric.",
                            interactive)
    if err:
        return err
    else:
        return (realm.upper())


def validate_netbios(domain, interactive):
    err = []
    if len(domain) < 1 or len(domain) > 15:
        err = error_msg("Netbios domain (aka workgroup) must be greater than 0"
                        " and less than 15 characters (7+ recommend).",
                        interactive)
    if not domain.isalnum():
        err = error_msg("Netbios domain (aka workgroup) must only contain"
                        " alphanumeric characters.",
                        interactive)
    if err:
        return err
    else:
        return (domain.upper())


def rm_f(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def rm_glob(path):
    file_list = glob.glob(path)
    for file_path in file_list:
        rm_f(file_path)


def run_command(command):
    proc = subprocess.Popen(command, encoding='utf-8',
                            stdout=PIPE, stderr=STDOUT)
    output = []
    while True:
        out = proc.stdout.read(1)
        if out == '' and proc.poll() is not None:
            break
        if out != '':
            output.append(out)
            sys.stdout.write(out)
            sys.stdout.flush()
    return proc.returncode, "".join(output)


def update_resolvconf(domain):
    resolvconf_head = '/etc/resolvconf/resolv.conf.d/head'
    with open(resolvconf_head, 'r') as fob:
        resolvconf = fob.readlines()
    new_resolvconf = []
    for line in resolvconf:
        for term in ['search', 'domain']:
            if line.startswith(term):
                line = '{} {}\n'.format(term, domain)
        new_resolvconf.append(line)
    with open(resolvconf_head, 'w') as fob:
        fob.writelines(new_resolvconf)


def update_hosts(ip, hostname, domain):
    """This function assumes default layout of hosts file; many circumstance
       may result in unexpected results. Only updates IPv4 results and will
       remove existing IPv6 values for FQDN."""
    fqdn = '.'.join([hostname, domain])
    hostsfile = '/etc/hosts'
    with open(hostsfile, 'r') as fob:
        hosts = fob.readlines()
    new_hosts = []
    found = False
    inserted = False
    for line in hosts:
        if fqdn in line:
            line = ''
        if found and not inserted:
            new_hosts.append('{} {}'.format(ip, fqdn))
            inserted = True
        if line.startswith('127.0.1.1'):
            found = True  # insert entry for this machine next line
        new_hosts.append(line)
    with open(hostsfile, 'w') as fob:
        fob.writelines(new_hosts)


def main():

    DEFAULT_REALM = "DOMAIN.LAN"
    DEFAULT_DOMAIN = "DOMAIN"
    DEFAULT_NS = ""

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help',
                                        'pass=',
                                        'domain=',
                                        'realm=',
                                        'join_ns='])
    except getopt.GetoptError as e:
        usage(e)

    interactive = False
    domain = ""
    realm = ""
    admin_password = ""
    join_nameserver = ""

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt == '--pass':
            admin_password = val
        elif opt == '--realm':
            realm = val
        elif opt == '--domain':
            domain = val
        elif opt == '--join_ns':
            join_nameserver = val
            DEFAULT_NS = join_nameserver

    if (
            (not (realm and domain and admin_password)) or
            (join_nameserver and not valid_ip(join_nameserver)) or
            TURNKEY_INIT):
        interactive = True
        if join_nameserver:
            create = True
    elif realm and domain and admin_password and join_nameserver:
        join_nameserver = valid_ip(join_nameserver)
        create = False
    elif realm and domain and admin_password and not join_nameserver:
        create = True

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
                "You can create new Active Directory or join existing one.",
                "Create",
                "Join")
            if create:
                create = True

        if not realm:
            while True:
                d = Dialog('Turnkey Linux - First boot configuration')
                realm = d.get_input(
                    "Samba Kerberos Realm / AD DNS zone",
                    "Kerberos Realm should be 2 or more groups of 63 or less"
                    " ASCII characters, separated by dot(s). Kerberos realm"
                    " will be stored as uppercase; DNS zone as"
                    " lowercase\n\n"
                    "Enter the Realm / DNS zone you would like to use.",
                    DEFAULT_REALM)
                realm = validate_realm(realm, interactive)
                if realm[0]:
                    break
                else:
                    d.error(realm[1])
                    continue
        else:
            realm = validate_realm(realm, interactive)

        if not domain:
            while True:
                d = Dialog('TurnKey Linux - First boot configuration')
                domain = d.get_input(
                    "Samba NetBIOS Domain (aka workgroup)",
                    "The NetBIOS domain (aka workgroup) should be 15 or less"
                    " ASCII characters.\n\n"
                    "Enter NetBIOS domain (aka 'WORKGROUP') to use.",
                    DEFAULT_DOMAIN)
                domain = validate_netbios(domain, interactive)
                if domain[0]:
                    break
                else:
                    d.error(domain[1])
                    continue
        else:
            domain = validate_netbios(domain, interactive)

        if not admin_password:
            d = Dialog('TurnKey Linux - First boot configuration')
            admin_password = d.get_password(
                    "Samba Password",
                    "Enter password for the samba 'Administrator' account.",
                    pass_req=8, min_complexity=3, blacklist=['(', ')'])

        if interactive and not create:
            d = Dialog('Turnkey Linux - First boot configuration')
            while True:
                join_nameserver = d.get_input(
                    "Add nameserver",
                    "Set DNS server IPv4 for existing AD domain DNS server",
                    DEFAULT_NS)
                if not valid_ip(join_nameserver):
                    d.error("IP: '{}' is not valid.".format(join_nameserver))
                    join_nameserver = ""
                    continue
                else:
                    break

        # Stop any Samba services
        services = ['samba', 'samba-ad-dc', 'smbd', 'nmbd']
        for service in services:
            subprocess.run(['systemctl', 'stop', service], stderr=PIPE)
        # Remove Samba & Kerberos conf
        rm_f('/etc/samba/smb.conf')
        rm_f('/etc/krb5.conf')
        # Remove Samba DBs
        dirs = ['/var/run/samba', '/var/lib/samba',
                '/var/cache/samba', '/var/lib/samba/private']
        for _dir in dirs:
            for _db_file in ['*.tdb', '*.ldb']:
                rm_glob('/'.join([_dir, _db_file]))

        if create:
            samba_domain = ['samba-tool', 'domain', 'provision',
                            '--server-role=dc', '--use-rfc2307',
                            '--dns-backend=SAMBA_INTERNAL',
                            '--realm={}'.format(realm),
                            '--domain={}'.format(domain),
                            '--adminpass={}'.format(admin_password),
                            '--option=dns forwarder=8.8.8.8',
                            '--option=interfaces=127.0.0.1 {}'.format(NET_IP)]
        else:  # join
            samba_domain = ['samba-tool', 'domain', 'join',
                            realm, 'DC',
                            '-U"{}\\Administrator"'.format(domain),
                            '--password={}'.format(admin_password),
                            '--option=idmap_ldb:use rfc2307 = yes']

        set_expiry = ['samba-tool', 'user',
                      'setexpiry', ADMIN_USER, '--noexpiry']
        export_krb = ['samba-tool', 'domain',
                      'exportkeytab', '/etc/krb5.keytab']

        finalize = False
        for samba_command in [samba_domain, set_expiry, export_krb]:
            samba_run_code, samba_run_out = run_command(samba_command)
            if samba_run_code != 0:
                if interactive:
                    d = Dialog('Turnkey Linux - First boot configuration')
                    retry = d.error("{}\n\n".format(samba_run_out))
                    finalize = False
                    DEFAULT_REALM = realm
                    realm = ""
                    DEFAULT_DOMAIN = domain
                    domain = ""
                    admin_password = ""
                    DEFAULT_NS = join_nameserver
                    join_nameserver = ""
                    break
                else:
                    fatal("Errors in processing domain-controller inithook"
                          " data.")
            else:
                finalize = True

        if finalize:
            os.chown('/etc/krb5.keytab', 0, 0)
            os.chmod('/etc/krb5.keytab', 0o600)
            shutil.copy2('/var/lib/samba/private/krb5.conf', '/etc/krb5.conf')
            update_resolvconf(realm.lower())
            subprocess.run(['systemctl', 'restart', 'resolvconf.service'])
            update_hosts(NET_IP, HOSTNAME.lower(), realm.lower())
            subprocess.run(['systemctl', 'start', 'samba-ad-dc'])
            while subprocess.run(['systemctl', 'is-active',
                                  '--quiet', 'samba-ad-dc']).returncode != 0:
                time.sleep(1)
            subprocess.check_output(['kinit', ADMIN_USER],
                                    encoding='utf-8',
                                    input=admin_password)
            msg = "\nPlease ensure that you have set a static IP. If you" \
                  " haven't already, please ensure that you do that ASAP," \
                  " and update IP addresses in DNS and hosts file (please" \
                  " see docs for more info)."
            if interactive:
                d = Dialog('Turnkey Linux - First boot configuration')
                d.infobox(msg)
            else:
                print(msg)
            break


if __name__ == "__main__":
    main()
