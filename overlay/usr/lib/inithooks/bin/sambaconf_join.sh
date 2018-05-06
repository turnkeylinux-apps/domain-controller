#!/bin/bash -e

while getopts d:r:u:p:n:h: option
    do
        case "${option}"
        in
        d) DOMAIN=${OPTARG};;
        r) REALM=${OPTARG};;
        u) ADMIN_USER=${OPTARG};;
        p) ADMIN_PASSWORD=${OPTARG};;
        n) NAME_SERVER=${OPTARG};;
    esac
done
	
# update nameservers
if [ ${#NAME_SERVER} -gt 0 ]
then
    sed -i "s/nameserver.*/nameserver $NAME_SERVER/" /etc/resolvconf/resolv.conf.d/head
    resolvconf -u
fi

# stop Samba service(s) - in case it's already running
/etc/init.d/samba stop >/dev/null || true
/etc/init.d/samba-ad-dc stop >/dev/null || true

# just in case Samba4 has been set up Samba3 style
/etc/init.d/smbd stop >/dev/null || true
/etc/init.d/nmbd stop >/dev/null || true

hostname dc2

rm /etc/samba/smb.conf || true

samba-tool domain join $REALM DC -U"$DOMAIN\\$ADMIN_USER" --password=$ADMIN_PASSWORD --dns-backend=SAMBA_INTERNAL

samba-tool user setexpiry $ADMIN_USER --noexpiry

samba-tool domain exportkeytab /etc/krb5.keytab

chown root:root /etc/krb5.keytab; chmod 600 /etc/krb5.keytab

ln -sf /var/lib/samba/private/krb5.conf /etc/krb5.conf
 
sed -i "s/domain.*/domain $REALM/" /etc/resolvconf/resolv.conf.d/head
sed -i "s/search.*/search $REALM/" /etc/resolvconf/resolv.conf.d/head

service samba-ad-dc start

sleep 5

REALM=$(echo "$REALM" | tr '[:lower:]' '[:upper:]')

echo $ADMIN_PASSWORD | kinit $ADMIN_USER@$REALM

/etc/init.d/samba-ad-dc restart >/dev/null || true

