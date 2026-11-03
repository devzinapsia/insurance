============================================
Gestión de seguros - Diferidos de Enterprise
============================================

Bridge between **Gestión de seguros** (``insurance_management``) and the
deferred expenses of Odoo Enterprise (``account_accountant``). It installs
automatically when both modules are present.

It adds the accrual method **Enterprise deferred expenses**: the bills created
from the policies keep the expense account on their line and carry the
validity of the policy (or of the endorsement, from its effective date) as
deferral start and end dates. Odoo Enterprise then creates the deferral
entries, so the premium is expensed month by month without the accrual plan of
the base module.

**Table of contents**

.. contents::
   :local:

Configuration
=============

#. In *Accounting > Configuration > Settings*, section *Deferred expenses*,
   set the deferred expense account and when the deferral entries are
   generated (on bill validation or manually).
#. In *Insurance > Configuration > Settings*, choose the accrual method
   *Enterprise deferred expenses* as the default of new policies. Each policy
   can still use another method in its *Accounting* tab.

Usage
=====

#. Create the bill of a policy (or of an endorsement) as usual.
#. Its line shows the deferral start and end dates of the policy validity.
#. When the bill is posted, Odoo Enterprise creates the deferral entries
   (or they are generated from the deferred expenses report if the
   generation is manual).

Running policies loaded at go-live (initial load): the bill of the
installments managed in Odoo is deferred from the go-live date to the end of
the policy. The premium of the historical installments is not billed again.

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
