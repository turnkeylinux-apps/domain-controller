WEBMIN_FW_TCP_INCOMING = 22 80 88 135 139 389 443 445 464 631 3268 12320 12321
WEBMIN_FW_UDP_INCOMING = 123 137 138

BACKPORTS=y # install samba v4.17 from backports

COMMON_OVERLAYS = lighttpd samba-sid-inithook
COMMON_CONF = samba-webmin

include $(FAB_PATH)/common/mk/turnkey/tkl-webcp.mk
include $(FAB_PATH)/common/mk/turnkey.mk
