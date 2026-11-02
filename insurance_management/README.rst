==================
Gestión de seguros
==================

Manages the insurance policies the company itself contracts (the company is
the insured party, not a broker): policies by branch, their validity, renewal
and non-renewal, insured objects, expiry alerts, documents and settings.

This module is delivered in phases (see ``docs/ROADMAP.md`` in the
repository). Phase 1, "expiry control", has no accounting: invoices,
installments, endorsements and accrual arrive in phase 2; fleet and employee
integrations, claims, surety bonds and the dashboard in phase 3.

Currently included:

* **Security**: an *Insurance* privilege with two groups. *User* can view,
  create and edit policies, renew them and mark them as not to be renewed.
  *Administrator* can also manage the configuration (branches, document types)
  and the insurance settings. Every new model has multi-company record rules.
* **Contacts**: *Is an insurer* and *Is an insurance producer* flags on
  contacts (tab *Sales & Purchase*), with the *Insurers* and *Producers*
  search filters.
* **Branches**: lines of business (motor, surety bond, fire...) with their
  object type, default alert days and additional users to notify. Ten
  branches are installed as editable initial data; module updates never
  overwrite changes made to them.
* **Policies**: internal reference numbered per company and year
  (``SEG/2026/0001``), insurer's policy number, branch, insurer, producer,
  responsible, validity (from / to, the end date is the last covered day),
  duration in months, renewal type, currency, net and total premium, total
  sum insured, deductible (amount or percentage), coverages, tags and notes.
* **Lifecycle**: seven states — Draft, In force, Expiring, Expired, Renewed,
  Not renewed and Cancelled. Confirming requires the policy number and the
  validity; the state is then set from the dates (a policy confirmed after
  its end date goes straight to Expired). A policy stays in force on its end
  date and expires the day after. Expired, Renewed, Not renewed and Cancelled
  policies are read-only (the chatter keeps working). Only an Administrator
  can reset a policy to draft. *Covered today* is true for confirmed,
  non-cancelled policies whose validity includes today.
* **Validations**: the end date must be after the start date; the duration
  must stay between the minimum and maximum months of the company (warning
  or block mode); the policy number is unique per insurer, company and start
  date, so a renewal can reuse the insurer's number.
* **Insured objects**: each policy lists the things or persons it covers,
  with sum insured, coverage, added / removed dates and, for vehicle
  branches, license plate, chassis and engine numbers. An object can point to
  an *insurable item* master (warehouse, shop, equipment...) that keeps its
  insurance history across policies. Objects of a confirmed policy are never
  deleted: they are removed with a date and a reason and stay as history; the
  total sum insured only counts active objects.
* **Contacts**: insurers and producers show a *Policies in force* smart
  button.
* **Renewal**: *Renew* is available on Expiring and Expired policies (late
  renewal). It creates the next policy as a draft with the same branch,
  insurer, producer, responsible, coverages, deductible, tags and active
  insured objects (keeping their insurable item link), starting the day
  after the end date and lasting the same. The new number stays empty until
  the insurer issues it, unless *Keep number on renewal* is set. Both
  policies are linked both ways and a *Renewals* smart button shows the
  whole history. The original policy keeps its state (and stays covered)
  until its end date; the day after it becomes Renewed. A late renewal of an
  Expired policy becomes Renewed right away. Deleting the renewal draft puts
  the original policy back where its own decision leads.
* **Non-renewal**: *Do not renew* can be used any time before the end date
  (In force or Expiring) with a mandatory reason. It can email the
  *Non-renewal instruction* to the producer (optional copy to the insurer and
  the responsible); the email stays in the chatter and the sending date is
  recorded. The policy stays in force until its end date and then becomes Not
  renewed. Renewing afterwards is still possible: the decision switches to
  *Renew* and the chatter warns if the instruction had already been sent.
* **Renewal request**: *Request renewal* opens the email composer with the
  *Renewal request* template for the producer (current objects and
  coverages, no amounts); the sending date is recorded.
* **Documents**: a *Documents* tab on the policy lists every file attached
  to it. *Upload document* asks for the file and a mandatory *document type*
  (Policy, Endorsement, Coverage certificate, Payment receipt, Invoice, Claim
  report, Other — an editable list in **Insurance ‣ Configuration ‣ Document
  types**). Files attached from the chatter also appear in the tab (and in
  the *Documents* smart button count); their type can be set afterwards.
  Documents can still be added to Expired, Renewed, Not renewed or Cancelled
  policies. The Enterprise *Documents* app is not used.
* **Views and reports**: policies open in a kanban grouped by state (all
  seven columns always shown), plus list, form, calendar by end date, pivot
  and graph. Search filters: *In force*, *Expire in 30 days*, *Expired
  without renewal*, *Expires today*, *Covered today*, *Draft*, *Not to be
  renewed*, *My policies*, an *End date* period filter, and group-bys by
  status, branch, insurer, producer, responsible and end date (month).
  **Insurance ‣ Reporting ‣ Upcoming expirations** lists the policies in
  force by end date (30 days by default) in list, calendar and pivot.
* **PDF reports**: *Policy sheet* (data, insured objects — active and
  removed — and coverages) and *Policies in force list* (ordered by end
  date), both in the *Print* menu of policies; **Insurance ‣ Reporting ‣
  Policies in force (PDF)** prints every policy in force of the allowed
  companies. Amounts only appear for users allowed to see them.
* **Emails**: both producer templates are editable (**Settings ‣ Technical ‣
  Email templates**), are written in the producer's language, use the
  company as sender and signature, and are email-client safe (tables, inline
  styles, 600 px, no external fonts, only the company logo served by Odoo).
  Rendered previews are kept in the module's ``preview/`` folder (not
  installed).

Expiry alerts
-------------

A scheduled action, *Insurance: policy expiry process*, runs every day at
07:00 Argentina time (10:00 UTC). For every policy In force or Expiring it:

#. **Moves the state**: In force → Expiring when the first alert threshold
   is reached (and always on the end date); the day after the end date →
   Renewed (a renewal exists), Not renewed (marked "do not renew") or
   Expired. Moving the end date of a policy away sets it back to In force.
#. **Sends the expiry notice** (template *Insurance: expiry notice*) to the
   users to notify, with an activity for the responsible:

   * **Thresholds, not exact days.** For each threshold of the policy (e.g.
     30, 15 and 7 days, plus the end date itself as an implicit 0), a notice
     is due once the days left are *equal or lower* than the threshold and
     that threshold was not notified yet. A day missed by the server is
     therefore caught up the next day.
   * **One notice when several thresholds are crossed at once.** A policy
     loaded with 10 days left and thresholds 30, 15 and 7 gets a single
     notice, for 15 (the threshold closest to the end date already reached);
     30 is recorded as covered, so the inbox is not flooded.
   * **Once per threshold.** Every notice is logged in the chatter and in
     the *Alerts sent* list of the policy (tab *Notifications*), per
     threshold and end date: running the process twice the same day sends
     nothing new. Changing the end date starts the notices over.
   * Subjects: "expires in N days", "expires tomorrow", "expires today".
   * Renewed policies (a renewal draft exists) get no more notices.
#. **Sends "Policy expired"** (template *Insurance: policy expired*) the
   day after the end date, if the policy was not renewed (also when it was
   marked not to renew), once.
#. **Sends the non-renewal instruction automatically** when the policy is
   set to *Automatic* sending, its renewal type is *Do not renew*, and the
   configured days before the end date are reached (once; copy to the
   responsible).

One email per recipient, in the recipient's own language and greeting them
by name, from the policy's company. Internal emails carry no amounts, as
some recipients may not be allowed to see them. Each policy is processed in
its own savepoint: an error on one policy is logged and never stops the
others. Policies are processed in batches of configurable size, committed
one by one.

Parameter hierarchy
-------------------

* **Alert days**: settings → branch → policy; the most specific level with a
  value wins (a policy with ``20,5`` ignores the branch and settings values).
* **Users to notify**: added up (union without duplicates) from the settings,
  the branch and the policy, plus the policy responsible.
* **Non-renewal instruction sending** (manual / automatic and days before):
  the settings give the default of new policies; each policy can change it.

Hiding costs
------------

With *Hide costs from users* on, the amounts of policies (net and total
premium, total sum insured, deductible), of insured objects (sum insured)
and of insurable items (reference value) are restricted to the
*Insurance: see amounts* access. This is enforced by the server (fields
protected by access groups): users without it cannot read, search, group or
write them, even through direct API calls, and their chatter hides amount
changes. Administrators always see amounts; other users can be given the
access individually in **Settings ‣ Users**. The setting applies to all
companies. Off by default.

Transitional editing rule (until endorsements arrive in phase 2)
-----------------------------------------------------------------

Endorsements do not exist yet, so a confirmed policy (In force or Expiring)
can still be corrected by insurance users and administrators. Every change is
traceable: key policy fields are tracked in the chatter, and every change to
its insured objects (added, modified, removed) is logged on the policy chatter
with the old and the new value. Once endorsements are available, insured
objects of a confirmed policy will only change through an endorsement and this
rule will be withdrawn.

What comes next
---------------

* **Phase 2 — economic and accounting management**: endorsements (they will
  replace the transitional editing rule and enable the Cancelled state),
  installments, vendor bills linked to policies, endorsements and
  installments, monthly accrual (module, Enterprise deferred expenses bridge
  or direct expense), payments (automatic debit, deferred payments and own
  deferred checks bridge, credit card), unpaid installments ("with debt"),
  foreign currency, initial load of running policies and Excel import, and
  the installment reports. ``account`` becomes a dependency then.
* **Phase 3 — claims, surety bonds and integrations**: Fleet and Employees
  bridge modules (vehicles and employees as insured objects, "Insurance (n)"
  history buttons, "insured today", insured payroll), claims and recovery
  accounting, surety bonds until release, and the insurance dashboard.
* **Backlog** (only on request): renewal quotations and year-on-year
  comparison, coverage certificates for third parties, producer portal.

**Table of contents**

.. contents::
   :local:

Configuration
=============

#. Give users access in **Settings ‣ Users**, *Insurance* privilege: *User*
   or *Administrator*.
#. Mark insurance companies and producers on their contacts: tab
   *Sales & Purchase*, group *Insurance*, flags *Is an insurer* and
   *Is an insurance producer*.
#. Review the branches in **Insurance ‣ Configuration ‣ Branches**
   (Administrator only). For each branch you can set:

   * *Object type*: vehicle, person, property, contract or generic.
   * *Alert days*: one or more thresholds separated by commas, e.g.
     ``30,15,7``. Leave empty to use the insurance settings value. A value
     on the policy takes precedence over the branch, and the branch over
     the settings.
   * *Users to notify*: added to the users of the settings and of the
     policy (union, without duplicates).
   * *Company*: leave empty to share the branch across companies.
#. Open **Insurance ‣ Configuration ‣ Settings** (insurance Administrator;
   Odoo administrator rights are not needed). Values apply to the current
   company, except the two marked as global:

   * *Alert days* (default ``30``) and *Users to notify*.
   * *Minimum* and *maximum policy duration* (default 1 and 12 months) and
     the *Policy duration check*: *Warning* (lets the policy be confirmed,
     with a warning and a chatter note) or *Block* (default).
   * *Coverage start and end time*, shown in the emails: 12:00 (default:
     the policy ends at noon of its end date) or 0:00 (it ends at 0:00 of
     the day after).
   * *Non-renewal instruction sending*: *Manual* (from the *Do not renew*
     button) or *Automatic* with the days before the end date. Default of
     new policies.
   * *Hide costs from users* (global, off by default) and the *Batch size of
     the daily process* (global, default 200).
   * Links to the branches and to the email templates.
#. Producers need an email address to receive the non-renewal instruction
   and the renewal request.
#. Review the document types in **Insurance ‣ Configuration ‣ Document
   types** (Administrator only); the initial ones can be renamed or archived.

Usage
=====

* Use the *Insurers* and *Producers* filters in **Contacts** to list the
  contacts marked with each flag.
* Branches are managed in **Insurance ‣ Configuration ‣ Branches**; the
  initial branches can be renamed, archived or adjusted freely.
* **Insurance ‣ Policies ‣ Policies** opens a kanban by state; switch to the
  calendar to see the end dates of the month. **Insurance ‣ Reporting ‣
  Upcoming expirations** shows what expires in the next 30 days.
* Create a policy in **Insurance ‣ Policies ‣ Policies**: choose the branch,
  insurer, producer and validity, load the premiums and add the insured
  objects. Save it as a draft until the insurer issues the number, then click
  **Confirm**.
* To take an object out of a confirmed policy, use the removal button of its
  line: enter the date and the reason. The object stays listed as removed.
* Insurable items are managed in **Insurance ‣ Policies ‣ Insurable items**,
  or created on the fly from an insured object line.
* From an insurer or producer contact, the *Policies in force* smart button
  lists their policies.
* When a policy is about to expire, click **Renew** to create the next
  policy as a draft; complete its number and premiums when the insurer
  issues it and confirm it.
* To stop a policy, click **Do not renew**, enter the reason and choose
  whether to email the instruction to the producer now.
* Click **Request renewal** to ask the producer for a renewal proposal.
* To print a policy, use **Print ‣ Policy sheet** from the policy (or from a
  selection in the list); **Insurance ‣ Reporting ‣ Policies in force (PDF)**
  prints the audit list of the policies in force.
* To attach a document, open the **Documents** tab of the policy and click
  **Upload document**: choose the document type and the file. Files dropped
  in the chatter appear in the same tab, highlighted until their type is set.
* Each policy has a **Notifications** tab: its own alert days and users to
  notify, the thresholds actually applied, the non-renewal sending mode and
  the list of alerts already sent. On its end date a policy shows an
  *Expires today* ribbon (also available as a search filter).

Testing the emails by running the process by hand
--------------------------------------------------

* From **Insurance ‣ Configuration ‣ Settings**, click **Run the expiry
  process now**; or, in developer mode, **Settings ‣ Technical ‣ Scheduled
  Actions ‣ Insurance: policy expiry process ‣ Run manually**.
* The emails are queued in **Settings ‣ Technical ‣ Emails** (developer
  mode). On a test database, leave the outgoing mail server unconfigured
  (or use a local fake SMTP server) so nothing is really sent.
* Running it again the same day sends nothing new; to see the next notice,
  move the policy end date closer.

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
