WEBMIN_FW_TCP_INCOMING = 22 80 135 139 443 445 631 12320 12321
WEBMIN_FW_UDP_INCOMING = 123 137 138

COMMON_OVERLAYS = lighttpd samba-sid-inithook tkl-webcp
COMMON_CONF = samba-webmin tkl-webcp

include $(FAB_PATH)/common/mk/turnkey.mk
