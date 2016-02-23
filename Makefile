WEBMIN_FW_TCP_INCOMING = 22 80 88 135 139 389 443 445 464 631 3268 12320 12321
WEBMIN_FW_UDP_INCOMING = 123 137 138

COMMON_OVERLAYS = lighttpd samba-sid-inithook tkl-webcp
COMMON_CONF = samba-webmin tkl-webcp

include $(FAB_PATH)/common/mk/turnkey.mk
