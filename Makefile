WEBMIN_FW_TCP_INCOMING = 22 80 88 135 139 389 443 445 464 631 3268 12321
WEBMIN_FW_UDP_INCOMING = 123 137 138

# uncomment these if/when newer samba needed (from backports)
#BACKPORTS=y
#BACKPORTS_PINS=samba* smbclient winbind libsmbclient libldb2 libtalloc2 libtdb1 libtevent0 libwbclient0 python3-tdb python3-ldb python3-samba python3-talloc

COMMON_OVERLAYS = lighttpd samba-sid-inithook
COMMON_CONF = samba-webmin

include $(FAB_PATH)/common/mk/turnkey/tkl-webcp.mk
include $(FAB_PATH)/common/mk/turnkey.mk
