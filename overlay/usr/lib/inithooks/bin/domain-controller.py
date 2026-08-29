#!/usr/bin/python3
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org> - all rights reserved
# Copyright (c) 2011-2026 TurnKey GNU/Linux <admin@turnkeylinux.org>
"""Configure Samba AD domain, realm and administrator password

Options:
    --pass-stdin    Read the AD domain 'Administrator' password from stdin.
                    The password must not contain '(' or ')' characters.
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
                    If '--pass-stdin', '--realm' & '--domain' set, but not
                    '--join_ns', this script will create a new domain. If
                    '--pass-stdin' &/or '--realm' &/or '--domain' not set,
                    will ask interactively.
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
                    If '--join_ns' not set, but 'hostname=' is, then
                    'hostname=' will be ignored.
                    DEFAULT=dc2 # only if joining a domain and run
                    interactively.
    --username=     To join an existing domain, you need to specify the domain
                    username to use. If run non-interactively and '--username'
                    not set, will assume DEFAULT. If joining an existing domain
                    interactively, then will ask (unless this switch is used).
                    DEFAULT=administrator
    --cups-printing=
                    valid options:
                        enable  | yes | true
                        disable | no  | false
                    enable or disable CUPS printing servers - skipped if run
                    from non-interactive firstboot but will ask otherwise.

Environment::

    _TURNKEY_INIT   If set, will assume the script is running under
                    'turnkey-init' and will run interactively. An initial
                    confirmation re reconfiguration will also be asked.

Notes:
------

Warning: previous configuration will be cleared!

To create a new AD domain non-interactively, pipe the password to stdin and set
'--pass-stdin', '--realm', '--domain' & --cups-printing.

To join an existing domain non-interactively, pipe the password to stdin and
set '--pass-stdin', '--realm', '--domain', '--join_ns', '--hostname' &
'--cups-printing' (and optionally '--username').

To run interactively, ensure that '--pass-stdin' &/or '--realm' &/or '--domain'
are _not_ set. Or set env var '_TURNKEY_INIT'. All required components that are
not provided valid values via commandline will be asked.
"""

import sys
import re
import os
import glob
import shutil
import getopt
import io
import socket
import ipaddress
import time
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from subprocess import PIPE, STDOUT

from libinithooks.dialog_wrapper import Dialog


ADMIN_USER = "administrator"
TURNKEY_INIT = os.getenv("_TURNKEY_INIT")
RESOLVCNF_HEAD = '/etc/resolvconf/resolv.conf.d/head'
RESOLVCNF_BAK = f'{RESOLVCNF_HEAD}.bak'
HOSTS_FILE = '/etc/hosts'
HOSTS_BAK = f'{HOSTS_FILE}.bak'
COMMAND_LOG = '/var/log/inithooks/samba_dc.log'


def usage(s=None):
    if s:
        print("Error:", s, file=sys.stderr)
    print(f"Syntax: {sys.argv[0]} [options]", file=sys.stderr)
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
    # IPv4Address rejects partial/short forms (e.g. "8", "8.8") that the
    # older socket.inet_aton() accepted and then wrote into resolv.conf.
    try:
        return str(ipaddress.IPv4Address(address))
    except ValueError:
        return False


def get_dns_forwarder(default='8.8.8.8'):
    """Return the host's current upstream (non-loopback) IPv4 nameserver to
    use as the samba DNS forwarder, falling back to a public resolver if none
    can be determined. Must be read before resolv.conf is rewritten to point
    at the local samba DNS, otherwise we'd just find 127.0.0.1."""
    try:
        with open('/etc/resolv.conf') as fob:
            for line in fob:
                fields = line.split()
                if len(fields) >= 2 and fields[0] == 'nameserver':
                    ns = valid_ip(fields[1])
                    if ns and not ipaddress.IPv4Address(ns).is_loopback:
                        return ns
    except FileNotFoundError:
        pass
    return default


def validate_realm(realm, interactive):
    err = []
    realm = realm.strip('.')
    if len(realm) > 255:
        err = error_msg("Realm must be less than 255 characters.", interactive)
    for bit in realm.split('.'):
        if len(bit) < 1 or len(bit) > 63:
            err = error_msg("All realm segments must be greater than 0 and"
                            " less than 63 characters.",
                            interactive)
            # empty segment has no first char to validate below
            continue
        regex = r'^[a-zA-Z0-9-]*$'
        if not bit[0].isalpha() or not re.fullmatch(regex, bit):
            err = error_msg("All realm segment characters must be"
                            " alphanumeric and must start with a letter.",
                            interactive)
    if err:
        return err
    else:
        return (realm.upper())


def validate_netbios(domain, interactive):
    if len(domain) < 1 or len(domain) > 15:
        return error_msg("Netbios domain (aka workgroup) must be greater than"
                         " 0 and less than 15 characters (7+ recommend).",
                         interactive)
    if not domain.isalnum() or not domain[0].isalpha():
        return error_msg("Netbios domain (aka workgroup) must only contain"
                         " alphanumeric characters and start with a letter.",
                         interactive)
    else:
        return (domain.upper())


def validate_username(username, interactive):
    if not username.isprintable():
        return error_msg("Username must not include non-printable:"
                         " characters.", interactive)
    if username[-1] == ' ':
        return error_msg("Username must not end with a space",
                         interactive)
    backslash = r"\ "[0]
    invalid_chars = ['"', '/', '[', ']', ':', ';', backslash,
                     '|', '=', ',', '+', '*', '?', '<', '>']
    found_chars = []
    for char in username:
        if char in invalid_chars:
            found_chars.append(char)
    if found_chars:
        return error_msg(f"Valid usernames can not include some special"
                         f" characters. Invalid characters are:"
                         f" {' '.join(invalid_chars)}",
                         interactive)
    return (username)


def dns_reachable(nameserver, timeout=3):
    """Check that a DNS server is reachable. Loopback is always treated as
    reachable because during new-domain provisioning resolv.conf is pointed at
    the not-yet-started local samba DNS. For a remote server, try a TCP
    connection to port 53 - more reliable than ICMP, which is commonly
    firewalled even when DNS itself answers."""
    ns = valid_ip(nameserver)
    if not ns:
        return False
    if ipaddress.IPv4Address(ns).is_loopback:
        return True
    try:
        with socket.create_connection((ns, 53), timeout=timeout):
            return True
    except OSError:
        return False


def check_dns(fqdn):
    proc = subprocess.run(['host', '-s', fqdn])
    if proc.returncode == 0:
        return True
    return False


def validate_hostname(hostname, domain, interactive):
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
        return error_msg(f"Host {fqdn} already registered on network.",
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
    proc = subprocess.Popen(command, text=True, stdin=PIPE if stdin else None,
                            stdout=PIPE, stderr=STDOUT)
    if stdin:
        output = proc.communicate(input=stdin)[0]
    else:
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


def run_samba_provision(command, admin_password):
    """Provision without placing the administrator password in process argv.

    samba-tool is a Python frontend. Calling its public entry point in-process
    keeps the password in Python memory and out of the kernel process list.
    The supplied command intentionally excludes --adminpass so it is also safe
    to display and retain in failure logs.
    """
    from samba.netcmd.main import samba_tool

    output_buffer = io.StringIO()
    with redirect_stdout(output_buffer), redirect_stderr(output_buffer):
        result = samba_tool(*command[1:], f'--adminpass={admin_password}')
    output = output_buffer.getvalue()
    if admin_password:
        output = output.replace(admin_password, '<REDACTED>')
    if output:
        sys.stdout.write(output)
        sys.stdout.flush()
    return (0 if result is None else result), output


def obtain_kerberos_ticket(username, admin_password, attempts=30, delay=1):
    """Wait for the newly started local KDC without exposing its password."""
    result = None
    for attempt in range(attempts):
        result = subprocess.run(
            ['kinit', username], input=admin_password, encoding='utf-8',
            stdout=PIPE, stderr=PIPE)
        if result.returncode == 0:
            return
        if attempt + 1 < attempts:
            time.sleep(delay)

    error = (result.stderr or '').strip()
    if admin_password:
        error = error.replace(admin_password, '<REDACTED>')
    raise RuntimeError(
        f'Kerberos did not become ready after {attempts} attempts: {error}')


def update_resolvconf(domain, nameserver, interactive):
    if not dns_reachable(nameserver):
        return error_msg(
            f"No DNS server is reachable (TCP/53) at IP address {nameserver}.",
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
                line = f'{term} {value}\n'
                print(f'Updating {term} ({value}) in resolv.conf')
        new_resolvconf.append(line)
    with open(RESOLVCNF_HEAD, 'w') as fob:
        fob.writelines(new_resolvconf)
    subprocess.run(['systemctl', 'restart', 'resolvconf.service'])


def restore_resolvconf():
    shutil.move(RESOLVCNF_BAK, RESOLVCNF_HEAD)
    subprocess.run(['systemctl', 'restart', 'resolvconf.service'])

def cups_status(enable):
    if enable:
        subprocess.run(["systemctl", "enable", "--now", "cups.service"])
    else:
        subprocess.run(["systemctl", "disable", "--now", "cups.service"])


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
    print(f'Updating {HOSTS_FILE}:')
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
    # 'hostname -I' returns every address on the host (IPv6 included), space
    # separated. Pick the first IPv4 - feeding the whole list into the samba
    # 'interfaces' option or the hosts file produces malformed config.
    net_ips = subprocess.run(['hostname', '-I'],
                             encoding='utf-8', stdout=PIPE).stdout.split()
    NET_IP = next((ip for ip in net_ips if valid_ip(ip)), "")

    # Capture the upstream resolver now, before update_resolvconf() repoints
    # resolv.conf at the local samba DNS.
    DNS_FORWARDER = get_dns_forwarder()

    DEFAULT_REALM = "DOMAIN.LAN"
    DEFAULT_DOMAIN = "DOMAIN"
    DEFAULT_NS = ""
    DEFAULT_NEW_HOSTNAME = "dc2"
    DEFAULT_ADMIN_USER = ADMIN_USER

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help',
                                        'pass-stdin',
                                        'domain=',
                                        'realm=',
                                        'join_ns=',
                                        'hostname=',
                                        'username='])
    except getopt.GetoptError as e:
        usage(e)

    interactive = False
    create = ""
    domain = ""
    realm = ""
    admin_password = ""
    join_nameserver = ""
    hostname = ""
    username = ""
    cups_printing = ""

    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt == '--pass-stdin':
            admin_password = sys.stdin.read()
        elif opt == '--realm':
            realm = val
        elif opt == '--domain':
            domain = val
        elif opt == '--join_ns':
            join_nameserver = val
            DEFAULT_NS = join_nameserver
        elif opt == '--hostname':
            hostname = val
        elif opt == '--username':
            username = val
        elif opt == '--cups-printing':
            cups_printing = val

    if (
            (not (realm and domain and admin_password)) or
            (join_nameserver and not valid_ip(join_nameserver) or
            (join_nameserver and not hostname))
            or TURNKEY_INIT):
        interactive = True
        if join_nameserver:
            # --join_ns means the user wants to JOIN an existing domain, not
            # create a new one. Drop an invalid value so the interactive flow
            # re-prompts for it rather than silently skipping the prompt.
            create = False
            if not valid_ip(join_nameserver):
                join_nameserver = ""
    elif realm and domain and admin_password and join_nameserver and hostname:
        join_nameserver = valid_ip(join_nameserver)
        update_resolvconf(realm.lower(), join_nameserver, interactive)
        hostname = validate_hostname(hostname, realm, interactive)
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
                "\n\nNote that joining a non-TurnKey existing AD domain is"
                " experimental and may fail. If so, please manually configure"
                " using the 'samba-tool' commandline tool.",
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

        if interactive and not create:
            d = Dialog('TurnKey Linux - First boot configuration')
            if not username:
                while True:
                    username = d.get_input(
                        "Existing Windows AD Domain Admin username",
                        "To join an existing domain, you need to authenticate"
                        " as an existing domain adminstrator.\n\n"
                        "Enter existing AD domain admin username.",
                        DEFAULT_ADMIN_USER)
                    username = validate_username(username, interactive)
                    if username[0]:
                        break
                    else:
                        d.error(username[1])

                        continue
        elif username and not create:
            username = validate_username(username, interactive)
            if not username[0]:
                fatal(username[1])
        else:
            username = DEFAULT_ADMIN_USER

        if not admin_password:
            d = Dialog('TurnKey Linux - First boot configuration')
            server_status = 'new' if create else 'existing'
            admin_password = d.get_password(
                    "Samba Password",
                    f"Enter password for the {server_status} samba Domain"
                    " 'Administrator' account.",
                    pass_req=8, min_complexity=3, blacklist=['(', ')'])

        if interactive:
            if cups_printing:
                if cups_printing.lower() in ["enable", "yes", "true"]:
                    cups_status(True)
                elif cups_printing.lower() in ["disable", "no", "false"]:
                    cups_status(False)
                else:
                    cups_printing = ""
            if not cups_printing:
                d = Dialog('TurnKey Linux - First boot configuration')
                cups_printing = d.yesno(
                    "Enable CUPS networking printing?",
                    "\n\nUnless you intend to share printers via your Domain"
                    " Controller, it is recommended to that CUPS printing"
                    " service is disabled.",
                    yes_label="Disable",  # returns True
                    no_label="Enable"  # returns False
                    )
                cups_status(not cups_printing)

        if interactive and not create:
            d = Dialog('Turnkey Linux - First boot configuration')
            if not join_nameserver:
                while True:
                    join_nameserver = d.get_input(
                        "Add nameserver",
                        "Set DNS server IPv4 for existing AD domain DNS"
                        " server",
                        DEFAULT_NS)
                    if not valid_ip(join_nameserver):
                        d.error(f"IP: '{join_nameserver}' not valid.")
                        join_nameserver = ""
                        continue
                    else:
                        break
            update_resolvconf(realm.lower(), join_nameserver, interactive)
            if not hostname:
                while True:
                    hostname = d.get_input(
                        "Set new hostname",
                        "Set new unique hostname for this domain-controller.",
                        DEFAULT_NEW_HOSTNAME)
                    hostname = validate_hostname(hostname, realm.lower(),
                                                 interactive)
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
                      'setexpiry', username, '--noexpiry']
        export_krb = ['samba-tool', 'domain',
                      'exportkeytab', '/etc/krb5.keytab']

        if create:
            ip = NET_IP  # will add to hosts file
            samba_domain = ['samba-tool', 'domain', 'provision',
                            '--server-role=dc', '--use-rfc2307',
                            '--dns-backend=SAMBA_INTERNAL',
                            f'--realm={realm}',
                            f'--domain={domain}',
                            f'--option=dns forwarder={DNS_FORWARDER}',
                            f'--option=interfaces=127.0.0.1 {NET_IP}']
            commands = [(samba_domain, None, admin_password),
                        (set_expiry, None, None),
                        (export_krb, None, None)]
            nameserver = '127.0.0.1'
            hostname = HOSTNAME
        else:  # join
            with open('/etc/krb5.conf', 'w') as fob:
                fob.write('[libdefaults]\n')
                fob.write('    dns_lookup_realm = false\n')
                fob.write('    dns_lookup_kdc = true\n')
                fob.write(f'    default_realm = {realm}')
            ip = None  # will update 127.0.1.1 hosts entry only
            config_krb = ['kinit', username]
            samba_domain = ['samba-tool', 'domain', 'join',
                            realm.lower(), 'DC',
                            '--option=idmap_ldb:use rfc2307 = yes']
            commands = [(config_krb, admin_password, None),
                        (samba_domain, None, None),
                        (export_krb, None, None)]
            nameserver = join_nameserver

        finalize = False

        update_resolvconf(realm.lower(), nameserver, interactive)
        print('hostname', hostname, 'realm', realm)
        update_hosts('127.0.1.1', hostname, realm)
        if ip:
            update_hosts(ip, hostname, realm)

        for samba_command, stdin_secret, provision_password in commands:
            print(f'Running command: {" ".join(samba_command)}')
            if provision_password is not None:
                samba_run_code, samba_run_out = run_samba_provision(
                        samba_command, provision_password)
            elif stdin_secret is not None:
                samba_run_code, samba_run_out = run_command(samba_command,
                                                            stdin=stdin_secret)
            else:
                samba_run_code, samba_run_out = run_command(samba_command)
            if samba_run_code != 0:
                os.makedirs(os.path.dirname(COMMAND_LOG), exist_ok=True)
                with open(COMMAND_LOG, 'a') as fob:
                    fob.write(f"Command: {' '.join(samba_command)}\n\n\n")
                    fob.write(f"{samba_run_out}\n")

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
                    lines_to_print.append(
                            f"See {COMMAND_LOG} for full output")
                    err_text = '\n'.join(lines_to_print)
                    retry = d.error(f"{err_text}\n\n")
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
                          f" data:\n{samba_run_out}")
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
            obtain_kerberos_ticket(username, admin_password)
            msg = "\nPlease ensure that you have set a static IP. If you" \
                  " haven't already, please ensure that you do that ASAP," \
                  " and update IP addresses in DNS and hosts file (please" \
                  " see docs for more info).\n"

            if create:
                msg = (f"{msg}\nWhen adding clients, you'll need this info:\n"
                       f"    nameserver: <IP_ADDRESS_OF_THIS_DC>\n"
                       "    * - set client to use this nameserver first!\n"
                       f"    AD DNS domain: {realm.lower()}\n"
                       f"    AD admin account name: {username}\n"
                       "    AD admin user password: <PASSWORD_SET>\n")

            if interactive:
                d = Dialog('Turnkey Linux - First boot configuration')
                d.msgbox("Samba connection info", msg)
            else:
                print(msg)
            cleanup()
            break
        else:
            restore_resolvconf()
            restore_hosts()


if __name__ == "__main__":
    main()
