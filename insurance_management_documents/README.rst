===============================
Gestión de seguros - Documentos
===============================

Bridge between **Gestión de seguros** (``insurance_management``) and the
Enterprise **Documents** app (``documents``). It installs automatically when
both modules are present (also on the update of ``insurance_management``).

* Every file attached to a policy or a claim (Documents tab, upload wizard
  or chatter) also becomes a document of the **Insurance** folder of the
  Documents app, with the tag *Insurance policy* or *Insurance claim* and
  the insurer as contact. The document stays linked to its policy or claim.
* On install, the files attached before are added the same way.
* The folder is **restricted**: only its members and the Documents system
  administrators see it. Insurance users keep seeing every file from the
  policies and claims, without any Documents right.
* Moving a document to the trash in Documents keeps the file on the policy;
  deleting it for good deletes it from the policy too.

**Table of contents**

.. contents::
   :local:

Configuration
=============

* In **Documents ‣ Configuration ‣ Settings**, section *Files
  centralization*: *Centralize insurance documents* (on by default) and the
  folder (default *Insurance*), per company.
* To let users browse the folder in Documents: they need the *Documents*
  access *User* and to be a member of the folder. A Documents system
  administrator (or a member with edit rights) opens the folder, **Share**,
  and adds them with *Viewer* or *Editor*. To open it to every internal
  user, set the folder access for internal users to *Viewer*.

Usage
=====

#. Upload a document to a policy or a claim as usual.
#. In **Documents**, folder *Insurance*: the file appears with its tag and
   the insurer, and opens its policy or claim.

Bug Tracker
===========

Bugs are tracked on
`GitHub Issues <https://github.com/devzinapsia/insurance/issues>`_.
In case of trouble, please check there if your issue has already been
reported.

Credits
=======

Authors
-------

* Zinapsia

Maintainers
-----------

This module is maintained by Zinapsia.

This module is part of the
`insurance <https://github.com/devzinapsia/insurance>`_ project.
