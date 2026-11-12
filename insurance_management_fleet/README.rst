==========================
Gestión de seguros - Flota
==========================

Bridge between **Gestión de seguros** (``insurance_management``) and
**Fleet** (``fleet``). It installs automatically when both modules are
present.

* Insured objects of vehicle branches (and endorsement lines adding
  objects) get a *Fleet vehicle*. It is linked automatically by license
  plate, or by chassis number without a plate match, comparing them in
  uppercase and without spaces, dashes nor dots, within the company of the
  policy. When several active vehicles match, or only an archived one, the
  object is not linked and the policy chatter says why. Vehicles are never
  created.
* On install, the insured objects loaded before are linked the same way.
* Renewals and endorsements keep the vehicle.
* **Link fleet vehicles** (policy button, confirmed vehicle policies only):
  choose or change the vehicle of each insured object by hand, without an
  endorsement (the change is logged on the policy).
* The vehicle form shows the *Insurance* smart button (every policy, with
  *Insured* / *Not insured* today) and the *Claims* button; the vehicle list
  and search get *Insured today* and *Without insurance in force*.
* Claims get the *Fleet vehicle*: choosing it proposes the policy and the
  object covering it on the date of occurrence.
* The dashboard shows the vehicles without insurance in force.
* Insurance users without Fleet rights can read the vehicles of the
  policies.

**Table of contents**

.. contents::
   :local:

Configuration
=============

* Mark *Requires fleet vehicle* on the vehicle branches whose objects must
  always be a fleet vehicle: confirming a policy (or an endorsement adding
  objects) then requires the vehicle.

Usage
=====

#. Load the vehicle policy as usual: typing the license plate links the
   vehicle, or choose it in the *Fleet vehicle* column.
#. From the vehicle, open *Insurance* to see its policies and *Claims* to
   see or load its claims.
#. Use the *Without insurance in force* filter of the vehicles to find the
   active vehicles without coverage.

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
