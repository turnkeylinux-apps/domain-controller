Domain Controller - Drop-in PDC replacement
===========================================

A Samba-based Windows PDC (Primary Domain Controller) server (without
the Windows) which is configured to support netlogon, network attached
storage for domain users, roaming profiles and PnP printing services
with an example PDF printing service. Includes a powerful web interface
for configuring Samba and printing services.

This appliance includes all the standard features in `TurnKey Core`_,
and on top of that:

- SSL support out of the box.
- Includes TurnKey web control panel (convenience).
- Webmin modules for configuring Samba.
- Includes flip to convert text file endings between UNIX and DOS
  formats.
- Domain controller (samba) configurations:
   
   - Sets domain name on first boot
   - Preconfigured netbios name: PDC
   - Created administrator account and added to Domain Users and Domain
     Admins.
   - Granted Domain Admins full permissions on the domain.
   - Created Samba related groups (smbusers, smbadmins, smbmachines).
   - Created group mapping for smbusers: Domain Users
   - Created group mapping for smbadmins: Domain Admins
   - Configured Samba and UNIX user/group synchronization (CLI and
     Webmin).
   - Configured netlogon service:
      
      - Limit domain login to Domain Users and Domain Admins.
      - Logon/home drive mapped to H:
      - Synchronize time at login with PDC.
      - Default permissions: owner full permissions.

   - Configured roaming profiles:
      
      - Public storage mapped to S:
      - Default permissions: owner full permissions, everyone read.

   - Configured printing support:
      
      - Setup Point-and-Print (PnP).
      - Installed PDF printer (drops printed docs to $HOME/PDF).
      - Configured cups web interface to bind to all interfaces and
        support SSL.

- Access your files securely from anywhere via `AjaXplorer`_:
   
   - Rich web GUI, with online previews for major formats and
     drag-n-drop support.
   - Dedicated `iOS`_ and `Android`_ apps for on-the-go access.
   - Pre-configured multi-authentication (Local and Samba).
   - Pre-configured repositories (storage, user home directory).

-  See the `Domain Controller documentation`_.

Credentials *(passwords set at first boot)*
-------------------------------------------

-  Webmin, Webshell, SSH, MySQL: username **root**
-  Samba: username **administrator**
-  Web based file manager (AjaXplorer):
   
   -  username **admin** (Local)
   -  username **administrator** (Samba)


.. _TurnKey Core: http://www.turnkeylinux.org/core
.. _AjaXplorer: http://ajaxplorer.info
.. _iOS: http://ajaxplorer.info/extensions/ios-client/
.. _Android: http://ajaxplorer.info/extensions/android/
.. _Domain Controller documentation: http://www.turnkeylinux.org/docs/domain-controller
