#!/bin/bash
set -euo pipefail

: "${TKL_TEST_RESULT:?TKL_TEST_RESULT must name the result file}"
: "${TKL_TEST_APP_PASS:?TKL_TEST_APP_PASS must contain the firstboot password}"

REALM=LOCALHOST.LAN
DOMAIN=LOCALHOST
RUNTIME_DIR=/run/tkl-v19-tests/domain-controller
AUTH_FILE=$RUNTIME_DIR/smb.auth
FIXTURE_SOURCE=$RUNTIME_DIR/netlogon-source.txt
FIXTURE_COPY=$RUNTIME_DIR/netlogon-copy.txt
JOIN_TARGET=$RUNTIME_DIR/join-dc
KRB5CCNAME=FILE:$RUNTIME_DIR/krb5cc
export KRB5CCNAME

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

require_contains() {
    local text=$1 expected=$2 context=$3
    [[ $text == *"$expected"* ]] \
        || fail "$context did not contain: $expected"
}

cleanup() {
    local status=$?
    trap - EXIT HUP INT TERM
    rm -rf "$RUNTIME_DIR"
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

install -d -m 0700 "$RUNTIME_DIR"

for service in samba-ad-dc lighttpd multi-user.target; do
    systemctl is-active --quiet "$service" || fail "$service is not active"
done
systemctl is-active --quiet cups.service \
    && fail "CUPS should remain disabled by default"
systemctl is-enabled --quiet cups.service \
    && fail "CUPS should not be enabled by default"

grep -Fq '[40domain-controller] successfully completed' /var/log/inithooks.log \
    || fail "Domain Controller firstboot hook did not complete"

python3 /run/tkl-v19-tests/tests/password-handoff.py
python3 - <<'PY'
import glob
import os
from pathlib import Path
import subprocess

secret = os.environ['TKL_TEST_APP_PASS'].encode()
for name in glob.glob('/var/log/inithooks*'):
    path = Path(name)
    if path.is_file() and secret in path.read_bytes():
        raise SystemExit(f'password retained in {name}')

journal = subprocess.run(
    ['journalctl', '--no-pager', '-u', 'inithooks.service'],
    check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout
if secret in journal:
    raise SystemExit('password retained in the inithooks journal')

for cmdline in glob.glob('/proc/[0-9]*/cmdline'):
    try:
        value = Path(cmdline).read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    if secret in value:
        raise SystemExit(f'password visible in process argv {cmdline}')
PY

role=$(testparm -s --parameter-name='server role' 2>/dev/null)
[[ $role = 'active directory domain controller' ]] \
    || fail "unexpected Samba server role: $role"
configured_realm=$(testparm -s --parameter-name=realm 2>/dev/null)
[[ $configured_realm = "$REALM" ]] \
    || fail "unexpected Samba realm: $configured_realm"

domain_info=$(samba-tool domain info 127.0.0.1)
require_contains "$domain_info" "Domain           : ${REALM,,}" \
    "Samba domain info"
require_contains "$domain_info" "Netbios domain   : $DOMAIN" \
    "Samba domain info"

host -W 3 -t SOA "${REALM,,}" 127.0.0.1 | grep -Fq 'has SOA record' \
    || fail "Samba DNS did not answer for ${REALM,,}"

[[ $(stat -c '%U:%G:%a' /etc/krb5.keytab) = root:root:600 ]] \
    || fail "Kerberos keytab permissions are not root:root 0600"
printf '%s' "$TKL_TEST_APP_PASS" | kinit "Administrator@$REALM"
klist -s || fail "Kerberos administrator ticket was not created"

cat > "$AUTH_FILE" <<EOF
username = Administrator
password = $TKL_TEST_APP_PASS
domain = $DOMAIN
EOF
chmod 0600 "$AUTH_FILE"
printf 'TurnKey Domain Controller v19 authenticated fixture\n' \
    > "$FIXTURE_SOURCE"
smbclient //127.0.0.1/netlogon --authentication-file="$AUTH_FILE" \
    --command="put $FIXTURE_SOURCE turnkey-v19-fixture.txt; get turnkey-v19-fixture.txt $FIXTURE_COPY; del turnkey-v19-fixture.txt" \
    >/dev/null
cmp "$FIXTURE_SOURCE" "$FIXTURE_COPY" \
    || fail "authenticated Netlogon round trip changed content"

# Exercise a disposable second-DC join against the created domain. The target
# database remains under /run and the whole runtime container is disposable.
samba-tool domain join "${REALM,,}" DC \
    --targetdir="$JOIN_TARGET" \
    --option='netbios name=JOINPROBE' \
    --option='interfaces=127.0.0.2' \
    --no-dns-updates --use-kerberos=required >/dev/null
[[ -s $JOIN_TARGET/private/sam.ldb ]] \
    || fail "disposable DC join did not create a replicated directory"

systemctl restart samba-ad-dc.service
systemctl is-active --quiet samba-ad-dc.service \
    || fail "Samba did not recover after restart"
samba-tool domain info 127.0.0.1 >/dev/null \
    || fail "Samba domain discovery failed after restart"
smbclient //127.0.0.1/netlogon --authentication-file="$AUTH_FILE" \
    --command='ls' >/dev/null \
    || fail "authenticated Netlogon access failed after restart"

control_panel=$(curl --fail --silent --show-error --location --max-time 30 \
    http://127.0.0.1/)
require_contains "$control_panel" 'TurnKey Domain Controller' \
    "Domain Controller web control panel"

installed_version=$(dpkg-query -W -f='${Version}' samba)
dpkg-query -W samba-ad-dc samba-common-bin krb5-user >/dev/null
before_version=$installed_version
apt-get update >/dev/null
policy=$(apt-cache policy samba)
candidate=$(awk '/Candidate:/ {print $2}' <<< "$policy")
[[ -n $candidate && $candidate != '(none)' ]] \
    || fail "APT has no Samba candidate"
apt-get indextargets --format '$(IDENTIFIER)|$(SUITE)|$(RELEASE)|$(SITE)' \
    | grep -E '^(Packages|Translation-[^|]+)\|(trixie|trixie-updates|trixie-security)\|' \
    >/dev/null || fail "APT has no eligible Trixie package index"
apt-get --simulate --only-upgrade install \
    samba samba-ad-dc samba-common-bin >/dev/null
[[ $(dpkg-query -W -f='${Version}' samba) = "$before_version" ]] \
    || fail "non-mutating update check changed Samba"

echo "PASS: create, authenticated Netlogon, disposable DC join, restart and APT"
cat > "$TKL_TEST_RESULT" <<EOF
package_source=Debian Trixie Samba packages
installed_version=samba $installed_version
runtime_checks=firstboot domain create, password non-disclosure, Samba DNS, Kerberos, authenticated Netlogon round trip, disposable second-DC join, restart persistence and web control panel passed
updater_command=apt-get update; apt-cache policy samba; apt-get --simulate --only-upgrade install samba samba-ad-dc samba-common-bin
updater_result=signed APT metadata selected candidate $candidate and the non-mutating upgrade simulation passed
updater_channel=Debian Trixie signed package repositories
integrity_evidence=installed dpkg state and apt-get signature verification bind Samba to signed Debian Trixie metadata
EOF
