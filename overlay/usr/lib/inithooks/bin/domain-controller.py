#!/usr/bin/python3
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org> - all rights reserved
# Copyright (c) 2011-2020 TurnKey GNU/Linux <admin@turnkeylinux.org>
"""Configure Samba AD domain, realm and administrator password

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
                    part of the realm, before the first dot/period.
                    DEFAULT=DOMAIN
   --join_ns=       To join an existing domain, you must provide the IPv4 of
                    the nameserver to use (plus the other 3 options).
                    If '--pass', '--realm' & '--domain' set, but not
                    '--join_ns', this script will create a new domain. If
                    '--pass' &/or '--realm' &/or '--domain' not set, will ask
                    interactively.
                    If '--join_ns' is set but is not a valid IPv4, will ask
                    interactively.
                    Also requires a valid '--hostname' (below) to be set.
    --hostname=     To join an existing domain, you must set a new unique
                    hostname for the new domain-controller (just the part
                    before the first dot - the realm/domain will be added).
                    If '--join_ns' is set but not 'hostname=', will ask
                    interactively.
                    If '--join_ns' & '--hostname' set, but '--hostname' is not
                    valid, will ask interactively.
                    If '--join_ns' not set, but 'hostname=' is, then 'hostname='
                    will be ignored.
                    DEFAULT=dc2 # only if joining a domain and run
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
--domain', '--join_ns' and '--hostname'.

To run interactively, ensure that '--pass' &/or '--realm' &/or '--domain' are
_not_ set. Or set env var '_TURNKEY_INIT'. All required components that are not
provided valid values via commandline will be asked.
"""

import sys
import re
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
RESOLVCNF_HEAD = '/etc/resolvconf/resolv.conf.d/head'
RESOLVCNF_BAK = '{}.bak'.format(RESOLVCNF_HEAD)
HOSTS_FILE = '/etc/hosts'
HOSTS_BAK = '{}.bak'.format(HOSTS_FILE)
COMMAND_LOG = '/var/log/inithooks/samba_dc.log'


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
        if not bit.isalnum() or not bit[0].isalpha():
            err = error_msg("All realm segment characters must be"
                            " alphanumeric and must start with a letter.",
                            interactive)
    if err:
        return err
    else:
        return (realm.upper())


def validate_netbios(domain, interactive):
    err = []
    if len(domain) < 1 or len(domain) > 15:
        return error_msg("Netbios domain (aka workgroup) must be greater than 0"
                         " and less than 15 characters (7+ recommend).",
                         interactive)
    if not domain.isalnum() or not domain[0].isalpha():
        return error_msg("Netbios domain (aka workgroup) must only contain"
                         " alphanumeric characters and start with a letter.",
                         interactive)
    else:
        return (domain.upper())


def ping_client(fqdn):
    proc = subprocess.run(['ping', '-c1', fqdn])
    if proc.returncode == 0:
        return True
    return False


def check_dns(fqdn):
    proc = subprocess.run(['host', '-s', fqdn])
    if proc.returncode == 0:
        return True
    return False


def get_hostname():
    return subprocess.run(['hostname', '-s'],
                          encoding='utf-8', stdout=PIPE).stdout.strip()


def validate_hostname(hostname, domain, interactive, default):
    if hostname == default:
        return error_msg(
                "Hostname matches default '{}'.".format(default),
                interactive)
    pattern = r"^[-\w]*$"
    if len(hostname.split('.')) > 1:
        return error_msg("Only the hostname (not the domain/realm) should be"
                         " supplied.",
                         interactive)
    match = re.match(pattern, hostname)
    if not match or (len(hostname) != len(match.group(0))):
        return error_msg("Invalid hostname &/or includes invalid characters.",
                         interactive)
    fqdn = '.'.join([hostname, domain]).lower()
    if check_dns(fqdn):
        return error_msg("Host {} already registered on network.".format(fqdn),
                         interactive)
    return (hostname)


def set_hostname(hostname):
    with open('/etc/hostname', 'w') as fob:
        fob.write(hostname+'\n')
    run_command(['hostname', hostname])


def rm_f(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def rm_glob(path):
    file_list = glob.glob(path)
    for file_path in file_list:
        rm_f(file_path)


def run_command(command, stdin=False):
    if not command:
        return 0, None
    if stdin:
        proc = subprocess.Popen(command, text=True, stdin=PIPE,
                                stdout=PIPE, stderr=STDOUT)
        output = proc.communicate(input=stdin)[0]
    else:
        proc = subprocess.Popen(command, text=True,
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
        output = "".join(output)
    return proc.returncode, output


def update_resolvconf(domain, nameserver, interactive):
    if not ping_client(nameserver):
        return error_msg(
                "No client is responding to ping at ip address {}.".format(nameserver),
                interactive)
    shutil.copy2(RESOLVCNF_HEAD, RESOLVCNF_BAK)
    with open(RESOLVCNF_HEAD, 'r') as fob:
        resolvconf = fob.readlines()
    new_resolvconf = []
    terms = ['nameserver', 'search', 'domain']
    for line in resolvconf:
        for term in terms:
            if line.startswith(term):
                if term == 'nameserver':
                    value = nameserver
                else:
                    value = domain
                line = '{} {}\n'.format(term, value)
                print('Updating {} ({}) in resolv.conf'.format(term, value))
        new_resolvconf.append(line)
    with open(RESOLVCNF_HEAD, 'w') as fob:
        fob.writelines(new_resolvconf)
    subprocess.run(['systemctl', 'restart', 'resolvconf.service'])


def restore_resolvconf():
    shutil.move(RESOLVCNF_BAK, RESOLVCNF_HEAD)
    subprocess.run(['systemctl', 'restart', 'resolvconf.service'])


def update_hosts(ip, hostname, domain):
    """This function assumes default layout of hosts file; many circumstance
       may result in unexpected results. Only updates IPv4 results and will
       remove existing IPv6 values for FQDN."""
    shutil.copy2(HOSTS_FILE, HOSTS_BAK)
    fqdn = '.'.join([hostname, domain]).lower()
    with open(HOSTS_FILE, 'r') as fob:
        hosts = fob.readlines()
    new_hosts = []
    localdomain = '127.0.1.1'
    print('Updating {}:'.format(HOSTS_FILE))
    for line in hosts:
        if not line.startswith('#'):
            if line.startswith(localdomain):
                line = ' '.join((localdomain, hostname, fqdn))+'\n'
                if ip != localdomain:
                    print(line.rstrip())
                    new_hosts.append(line)
                    line = ' '.join((ip, hostname, fqdn))+'\n'
            elif line.startswith(ip):
                line = ''
        print(line.rstrip())
        new_hosts.append(line)
    print('### End of hosts file ###')
    with open(HOSTS_FILE, 'w') as fob:
        fob.writelines(new_hosts)


def restore_hosts():
    shutil.move(HOSTS_BAK, HOSTS_FILE)


def cleanup():
    for backup in (RESOLVCNF_BAK, HOSTS_BAK):
        rm_f(backup)


def main():

    HOSTNAME = subprocess.run(['hostname', '-s'],
                              encoding='utf-8', stdout=PIPE).stdout.strip()
    NET_IP = subprocess.run(['hostname', '-I'],
                            encoding='utf-8', stdout=PIPE).stdout.strip()

    # disabled for now, will reimplment at some point...
    #NET_IP321 = NET_IP.split('.')[:-1]
    #NET_IP321.reverse()
    #NET_IP321 = '.'.join(NET_IP321)
    #NET_IP4 = NET_IP.split('.')[-1]

    DEFAULT_HOSTNAME = "dc1"
    DEFAULT_REALM = "DOMAIN.LAN"
    DEFAULT_DOMAIN = "DOMAIN"
    DEFAULT_NS = ""
    DEFAULT_NEW_HOSTNAME = "dc2"


    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help',
                                        'pass=',
                                        'domain=',
                                        'realm=',
                                        'join_ns=',
                                        'hostname='])
    except getopt.GetoptError as e:
        usage(e)

    interactive = False
    domain = ""
    realm = ""
    admin_password = ""
    join_nameserver = ""
    hostname = ""

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
        elif opt == '--hostname':
            hostname = val

    if (
            (not (realm and domain and admin_password)) or
            (join_nameserver and not valid_ip(join_nameserver) or
            (join_nameserver and not hostname))
            or TURNKEY_INIT):
        interactive = True
        if join_nameserver:
            create = True
    elif realm and domain and admin_password and join_nameserver and hostname:
        join_nameserver = valid_ip(join_nameserver)
        update_resolvconf(realm.lower(), join_nameserver, interactive)
        hostname = validate_hostname(hostname, realm, interactive, DEFAULT_HOSTNAME)
        if join_nameserver and hostname[0]:  # both valid
            create = False
        elif join_nameserver:  # invalid hostname
            restore_resolvconf()
            interactive = True
            hostname = ""
        elif hostname[0]:  # invalid nameserver IPv4
            interactive = True
        else:  # both invalid
            restore_resolvconf()
            interactive = True
            hostname = ""
            join_nameserver = ""
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
                "You can create new Active Directory or join existing one."
                "\n\nNote that joining a non-TurnKey existing AD domain not is"
                " experimental and may fail. If so, please manually configure"
                " using the 'sambatool' commandline tool.",
                "Create",
                "Join")
            if create:
                create = True
            else:
                create = False

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
            if create:
                server_status = 'new'
            else:
                server_status = 'existing'
            admin_password = d.get_password(
                    "Samba Password",
                    "Enter password for the {} samba Domain 'Administrator'"
                    " account.".format(server_status),
                    pass_req=8, min_complexity=3, blacklist=['(', ')'])
        if interactive and not create:
            d = Dialog('Turnkey Linux - First boot configuration')
            if not join_nameserver:
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
            # set up nameserver now, so we can check for existing client hostname
            update_resolvconf(realm.lower(), join_nameserver, interactive)
            if not hostname:
                while True:
                    hostname = d.get_input(
                        "Set new hostname",
                        "Set new unique hostname for this domain-controller.",
                        DEFAULT_NEW_HOSTNAME)
                    hostname = validate_hostname(hostname, realm.lower(), interactive, DEFAULT_HOSTNAME)
                    if not hostname[0]:
                        d.error(hostname[1])
                        continue
                    else:
                        set_hostname(hostname)
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

        set_expiry = ['samba-tool', 'user',
                      'setexpiry', ADMIN_USER, '--noexpiry']
        export_krb = ['samba-tool', 'domain',
                      'exportkeytab', '/etc/krb5.keytab']

        krb_pass = None
        if create:
            ip = NET_IP  # will add to hosts file
            samba_domain = ['samba-tool', 'domain', 'provision',
                            '--server-role=dc', '--use-rfc2307',
                            '--dns-backend=SAMBA_INTERNAL',
                            '--realm={}'.format(realm),
                            '--domain={}'.format(domain),
                            '--adminpass={}'.format(admin_password),
                            '--option=dns forwarder=8.8.8.8',
                            '--option=interfaces=127.0.0.1 {}'.format(NET_IP)]
            commands = [samba_domain, set_expiry, export_krb]
            nameserver = '127.0.0.1'
            hostname = HOSTNAME
        else:  # join
            with open('/etc/krb5.conf', 'w') as fob:
                fob.write('[libdefaults]\n')
                fob.write('    dns_lookup_realm = false\n')
                fob.write('    dns_lookup_kdc = true\n')
                fob.write('    default_realm = {}'.format(realm))
            ip = None  # will update 127.0.1.1 hosts entry only
            config_krb = ['kinit', 'administrator']
            krb_pass = admin_password
            samba_domain = ['samba-tool', 'domain', 'join',
                            realm.lower(), 'DC',
                            "--option='idmap_ldb:use rfc2307 = yes'"]
            commands = [config_krb, samba_domain, export_krb]
            nameserver = join_nameserver

        finalize = False

        update_resolvconf(realm.lower(), nameserver, interactive)
        print('hostname', hostname, 'realm', realm)
        update_hosts('127.0.1.1', hostname, realm)
        if ip:
            update_hosts(ip, hostname, realm)

        for samba_command in commands:
            print('Running command: {}'.format(' '.join(samba_command)))
            if krb_pass:
                samba_run_code, samba_run_out = run_command(samba_command,
                                                            stdin=krb_pass)
                krb_pass = None
            else:
                samba_run_code, samba_run_out = run_command(samba_command)
            if samba_run_code != 0:
                os.makedirs(os.path.dirname(COMMAND_LOG), exist_ok=True)
                with open(COMMAND_LOG, 'a') as fob:
                    fob.write("Command: {}\n\n".format(
                        " ".join(samba_command)))
                    fob.write("\n")
                    fob.write("{}\n".format(samba_run_out))

                if interactive:
                    d = Dialog('Turnkey Linux - First boot configuration')
                    # handle incorrect details
                    lines_to_print = []
                    end = False
                    for line in samba_run_out.split('\n'):
                        if line.startswith('Failed to bind'):
                            lines_to_print.append(
                                    "-".join(line.split("-", 2)[:2]))
                        elif line.startswith('Failed to connect'):
                            lines_to_print.append(
                                    line.split("-", 1)[:1][0])

                        elif line.startswith('ERROR'):
                            lines_to_print.append(
                                    "-".join(line.split("-", 2)[:2]))
                            end = True
                        else:
                            if not end:
                                lines_to_print.append(line)
                            continue
                    lines_to_print.append('')
                    lines_to_print.append("See {} for full output".format(COMMAND_LOG))
                    retry = d.error("{}\n\n".format('\n'.join(lines_to_print)))
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
                          " data:\n{}".format(samba_run_out))
            else:
                finalize = True

        if finalize:
            os.chown('/etc/krb5.keytab', 0, 0)
            os.chmod('/etc/krb5.keytab', 0o600)
            shutil.copy2('/var/lib/samba/private/krb5.conf', '/etc/krb5.conf')
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
                  " see docs for more info).\n"

            if create:
                msg = msg + \
                      "\nWhen adding clients, you'll need this info:\n" \
                      "    nameserver: {}\n" \
                      "    * - set client to use this nameserver first!\n" \
                      "    AD DNS domain: {}\n" \
                      "    AD admin account name: {}\n" \
                      "    AD admin user password: (what you set)\n" \
                      "".format(nameserver, realm.lower(), ADMIN_USER)

            if interactive:
                d = Dialog('Turnkey Linux - First boot configuration')
                d.infobox(msg)
            else:
                print(msg)
            cleanup()
            break
        else:
            restore_resolvconf()
            restore_hosts()


if __name__ == "__main__":
    main()
