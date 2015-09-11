Domain Controller - Active Directory (AD) server
================================================

A Samba-based Windows AD-DC (Active Directory Domain Controller) 
server (without the Windows) which is configured to support netlogon.

As of v14.0 the DC appliance is a 'barebones' AD compatible DC 
which uses Samba4. It also includes PnP printing services with an 
example PDF printing service. Includes a web interface for 
configuring Samba (Webmin) and printing services (CUPS).

This appliance includes all the standard features in `TurnKey Core`_,
and on top of that:

- SSL support out of the box.
- Includes TurnKey web control panel (convenience).
- Webmin modules for configuring Samba.
- Includes flip to convert text file endings between UNIX and DOS
  formats.
- Domain controller (samba) configurations:
   
   - Sets domain/realm names on first boot
   - Preconfigured netbios name: PDC
   - Created administrator account is pre-set as Domain User/Admin
   - Domain Admins have full permissions on the domain.
      - Default permissions: owner full permissions.


   - Configured printing support:
      
      - Installed PDF printer (drops printed docs to $HOME/PDF).
      - Configured cups web interface to bind to all interfaces and
        support SSL.


Important
---------
-  See the `Domain Controller documentation`_ for limitations and 
   requirements.

Credentials *(passwords set at first boot)*
-------------------------------------------

-  Webmin, Webshell, SSH, MySQL: username **root**
-  Samba: username **administrator**

.. _TurnKey Core: http://www.turnkeylinux.org/core
.. _Domain Controller documentation: http://www.turnkeylinux.org/docs/domain-controller
