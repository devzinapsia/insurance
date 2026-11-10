===================================
Gestión de seguros - Pagos de adhoc
===================================

Bridge between **Gestión de seguros** (``insurance_management``) and adhoc's
payments (``account_payment_pro``). It installs automatically when both
modules are present.

``account_payment_pro`` fills the debts of every new vendor payment with all
the open payable lines of the partner and, when the payment is posted,
reconciles the oldest ones first. The payments created for insurance
installments (automatic debit, scheduled transfer, deferred check) would then
list every debt with the insurer and could pay another bill. With this module
the payment of an installment carries only the installment line of its bill
in *Debts*, as when the payment is registered from the bill.

When installed, the draft payments of installments already created get their
debts fixed the same way.

**Table of contents**

.. contents::
   :local:

Configuration
=============

Nothing to configure: it installs with ``insurance_management`` and
``account_payment_pro``, and the update of ``insurance_management`` installs
it on databases that already have both.

Usage
=====

#. Generate the installments of a policy and post its bill.
#. Open the payment of an installment (draft payment modes) or let the daily
   process post it: the *Debts* tab shows only that installment line.
#. Post it: the installment is paid against its bill, and the other bills of
   the insurer stay open.

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
