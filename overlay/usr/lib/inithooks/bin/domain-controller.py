#!/usr/bin/python
# Copyright (c) 2010 Alon Swartz <alon@turnkeylinux.org> - all rights reserved
"""Configure samba domain and password

Options:
    --pass=      if not provided, will ask interactively
    --domain=    if not provided, will ask interactively
                 DEFAULT=DOMAIN
"""

import re
import sys
import getopt
import subprocess
from subprocess import PIPE

from executil import system
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

DEFAULT_DOMAIN="DOMAIN"

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], "h",
                                       ['help', 'pass=', 'domain='])
    except getopt.GetoptError, e:
        usage(e)

    domain = ""
    password = ""
    for opt, val in opts:
        if opt in ('-h', '--help'):
            usage()
        elif opt == '--pass':
            password = val
        elif opt == '--domain':
            domain = val

    if not domain:
        d = Dialog('TurnKey Linux - First boot configuration')
        domain = d.get_input(
            "Samba Domain",
            "Enter domain you would like to use.",
            DEFAULT_DOMAIN)

    if not password:
        if 'd' not in locals():
            d = Dialog('TurnKey Linux - First boot configuration')

        password = d.get_password(
            "Samba Password",
            "Enter new password for the samba 'administrator' account.")

    system("service smbd stop >/dev/null || true")

    # set domain
    if domain == "DEFAULT":
        domain = DEFAULT_DOMAIN

    new = []
    smbconf = "/etc/samba/smb.conf"
    for s in file(smbconf).readlines():
        s = s.rstrip()
        s = re.sub("workgroup = (.*)", "workgroup = %s" % domain.upper(), s)
        new.append(s)

    fh = file(smbconf, "w")
    print >> fh, "\n".join(new)
    fh.close()

    # set unix administrator password
    p = subprocess.Popen(["chpasswd"], stdin=PIPE, shell=False)
    p.stdin.write("administrator:%s" % password)
    p.stdin.close()
    err = p.wait()
    if err:
        fatal(err)

    # set smb administrator password
    p = subprocess.Popen(["smbpasswd","-s","administrator"], stdin=PIPE, shell=False)
    p.stdin.write("%s\n%s" % (password, password))
    p.stdin.close()
    err = p.wait()
    if err:
        fatal(err)

    system("service smbd start >/dev/null || true")

if __name__ == "__main__":
    main()

