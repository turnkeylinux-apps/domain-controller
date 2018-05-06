#!/bin/bash -e

while getopts d:r:u:p: option
    do
        case "${option}"
        in
        d) DOMAIN=${OPTARG};;
        r) REALM=${OPTARG};;
        u) ADMIN_USER=${OPTARG};;
        p) ADMIN_PASSWORD=${OPTARG};;
    esac
done

# stop Samba service(s) - in case it's already running
/etc/init.d/samba stop >/dev/null || true
/etc/init.d/samba-ad-dc stop >/dev/null || true

# just in case Samba4 has been set up Samba3 style
/etc/init.d/smbd stop >/dev/null || true
/etc/init.d/nmbd stop >/dev/null || true

rm /etc/samba/smb.conf || true

samba-tool domain provision --realm $REALM --domain $DOMAIN --adminpass $ADMIN_PASSWORD --server-role=dc --use-rfc2307 --option="dns forwarder = 8.8.8.8"

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
