WEBMIN_FW_TCP_INCOMING = 22 80 135 139 443 445 631 12320 12321
WEBMIN_FW_UDP_INCOMING = 123 137 138

COMMON_OVERLAYS = samba-sid-inithook tkl-webcp ajaxplorer
COMMON_CONF = tkl-webcp samba-webmin ajaxplorer lighttpd-fastcgi

include $(FAB_PATH)/common/mk/turnkey.mk
