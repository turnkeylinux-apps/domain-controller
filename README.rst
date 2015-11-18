Domain Controller - free Active Directory server
================================================

A Samba4-based Active Directory-compatible domain controller that
supports printing services and centralized Netlogon authentication for
Windows systems, without requiring Windows Server.  Since 1992, Samba
has provided a secure and stable free software re-implementation of
standard Windows services and protocols (SMB/CIFS).

This appliance includes all the standard features in `TurnKey Core`_,
and on top of that:

- SSL support out of the box.
- Webmin modules for configuring Samba.

- Domain controller (Samba) configurations:
   
  - Preconfigured NetBIOS name: PDC
  - Sets domain/realm names on first boot
  - Created administrator account is pre-set as Domain User/Admin
  - Domain Admins have full permissions on the domain.

    - Default permissions: owner full permissions.

  - Configured plug-and-play printing support:
     
     - Installed PDF printer (drops printed docs to $HOME/PDF).
     - Configured cups web interface to bind to all interfaces and
       support SSL.

- Includes **flip** to convert text file endings between UNIX and DOS
  formats.
- Includes TurnKey web control panel (convenience).

Important
---------

-  See the `Domain Controller documentation`_ for limitations and 
   requirements.

Credentials *(passwords set at first boot)*
-------------------------------------------

-  Webmin, Webshell, SSH, MySQL: username **root**
-  Samba: username **administrator**

.. _TurnKey Core: https://www.turnkeylinux.org/core
.. _Domain Controller documentation: https://www.turnkeylinux.org/docs/domain-controller
