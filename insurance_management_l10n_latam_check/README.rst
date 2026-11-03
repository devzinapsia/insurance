====================================
Gestión de seguros - Cheques propios
====================================

Bridge between **Gestión de seguros** (``insurance_management``) and the
checks of the Latin American localization (``l10n_latam_check``). It installs
automatically when both modules are present.

Installments paid with a **deferred check** payment mode whose payment method
is *Own checks* get a payment with one own check for the installment amount,
payable on the installment due date. The payments are created when the bill
is posted, as drafts to review, so the treasurer only fills in the check
number and posts them.

**Table of contents**

.. contents::
   :local:

Configuration
=============

#. In the bank journal the checks are issued from, add the outbound payment
   method *Own checks* with its outstanding payments account.
#. In *Insurance > Configuration > Payment modes*, create a payment mode of
   type *Deferred check* with that journal and payment method, and leave the
   payment state as *Draft* so the check number can be filled in.

Usage
=====

#. Use the deferred check payment mode on the policy (or on some of its
   installments) and generate the installments.
#. Post the bill of the policy: one draft payment per installment is created,
   each with its own check dated on the installment due date.
#. Open each payment, fill in the check number and post it. The installment
   is then marked as paid against the bill.

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
