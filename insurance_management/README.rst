==================
Gestión de seguros
==================

Manages the insurance policies the company itself contracts (the company is
the insured party, not a broker): policies by branch, their validity, renewal
and non-renewal, insured objects, expiry alerts, documents and settings.

This module is delivered in phases (see ``docs/ROADMAP.md`` in the
repository). Phase 1, "expiry control", and phase 2, "economic and accounting
management" (endorsements, installments, vendor bills, payments, accrual,
foreign currency, initial load and import), are included; fleet and employee
integrations, claims, surety bonds and the dashboard arrive in phase 3.

Two bridge modules install automatically when their dependency is present:
``insurance_management_account_accountant`` (Enterprise deferred expenses as
accrual method) and ``insurance_management_l10n_latam_check`` (own deferred
checks for the installments).

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
* **Lifecycle**: eight states — Draft, Not started, In force, Expiring,
  Expired, Renewed, Not renewed and Cancelled. Confirming requires the policy
  number and the validity; the state is then set from the dates: a policy
  whose start date is still ahead is Not started (not covered, no expiry
  notices; the daily process starts it on its start date), and a policy
  confirmed after its end date goes straight to Expired. If the premium
  and/or the total premium is zero, the Confirm button warns first (once
  confirmed they only change through an endorsement); the user can go back
  or confirm anyway, which is logged in the chatter. A policy stays in force on its end
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
  insurance history across policies: choosing it proposes its name and its
  reference value as sum insured, and the item shows a *Policies* smart
  button and an *Insurance history* tab. Objects of a confirmed policy are never
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

Endorsements (phase 2)
----------------------

Once a policy is confirmed, its contract data (number, branch, insurer,
producer, validity, currency, premiums, deductible, coverages) and its
insured objects **only change through endorsements** (**Insurance ‣
Policies ‣ Endorsements** or the *New endorsement* button of the policy, on
policies In force or Expiring). Administrative data (responsible, users to
notify, tags, notes, documents) stays editable. An administrator can still
reset a policy to draft to correct a loading mistake.

* Types (editable list in **Insurance ‣ Configuration ‣ Endorsement
  types**): add object, remove object, sum insured increase or reduction,
  coverage change, data change (e.g. new producer), validity extension and
  cancellation.
* Confirming an endorsement applies it: objects are added (dated with the
  endorsement effective date), removed (kept as history with the date, the
  reason and the endorsement) or changed (the previous sum insured is kept on
  the endorsement line and logged in the chatter); the total sum insured is
  recalculated; an extension moves the end date (it may exceed the maximum
  duration); a cancellation moves the policy to Cancelled.
* Each endorsement has its own premium difference: positive (additional
  premium, with its own bill and installments) or negative (refund, by
  default deducted from the next pending installments, or refunded by the
  insurer). The policy shows the total premium including endorsements.
* Confirmed endorsements are never deleted.

The phase 1 transitional editing rule (confirmed policies editable by hand,
with every change logged) has been withdrawn.

Accounting parameters (phase 2)
-------------------------------

* **Insurance product** (Settings): a service product whose taxes and
  expense account are proposed on every insurance bill; a branch can use its
  own product.
* **Expense account**: policy, else branch, else insurance product.
  **Prepaid insurance account** (module accrual): policy, else settings.
  **Analytic distribution**: policy, else branch.
* **Billing mode** (one bill per policy, with one due date per installment,
  or one bill per installment): settings, branch, policy.
* **Accrual method** (module accrual, Enterprise deferred expenses through
  the bridge module, or none): settings, policy.
* **Payment modes** (**Insurance ‣ Configuration ‣ Payment modes**): how
  installments are paid — automatic debit (bank or card), deferred check or
  echeq, scheduled transfer or manual — with the journal, the payment method
  and whether generated payments are posted or left as drafts to review.
  The journal method must have an outstanding payments account. The policy
  takes the default payment mode of the settings.
* **Go-live date** and **accounting users to notify** (settings).
* Accounting fields are only visible to accounting users, and only
  accounting administrators set up the product, accounts and journals in the
  insurance settings.

Installments (phase 2)
----------------------

* **Generate installments** (policy, or endorsement with an additional
  premium) creates monthly installments of equal amounts from the first due
  date; the last one absorbs the rounding. The number of installments, the
  first due date, the total and the payment mode are proposed from the
  policy and can be changed. Generating again replaces the installments while
  none of them is billed or paid.
* Each installment can be edited (amount, due date, payment mode) until it is
  billed or paid, e.g. when the insurer bills pro rata. The policy shows the
  installments total and its **difference** with the total premium including
  endorsements, which must be zero.
* States: Pending, Scheduled (a payment exists), Paid, Overdue (due date
  passed without payment) and Cancelled. Fiscal year closings never change
  the installments: all of them are generated so the future cash flow is
  complete.
* **Insurance ‣ Policies ‣ Installments** lists them (editable list, pivot
  and graph); **Insurance ‣ Reporting ‣ Installments per month** shows per
  month what is pending, scheduled and paid, in company currency.

Vendor bills (phase 2)
----------------------

* **Create bill** (policy or endorsement) creates the draft vendor bill of
  the installments: one bill per policy with one due date per installment
  (a payment term is generated for the bill), or one bill per installment,
  according to the billing mode. The line uses the insurance product (its
  taxes) on the net premium share, the account of the accrual method and the
  analytic distribution.
* Posting the bill links each payable line with its installment. Bills keep
  the policy (and endorsement / installment) link; the policy shows a *Bills*
  smart button with the balance due, and policies with posted bills or
  payments can no longer be reset to draft.
* An endorsement with a negative premium creates a **credit note**: by
  default it is reconciled with the next pending installments (nearest due
  date first); otherwise it waits for the insurer's refund.
* Resetting a bill to draft and posting it again links the installments
  again, reconciles the payments already posted and rebuilds the accrual
  plan if the amount changed (and no month was accrued yet). Cancelling a
  bill releases its installments, which can then be edited and billed
  again; a bill with accrued months must be corrected with a credit note.
* An opening bill (debt with the insurer at go-live) can be linked to a
  running policy afterwards, even posted.

Payments (phase 2)
------------------

* Every installment has a payment mode. Payments are created with the
  installment amount, the journal and method of the mode, and posted or left
  as drafts according to the mode; a draft payment is reconciled with its
  installment when it is posted.
* **Automatic debit**: the daily process *Insurance: installments* creates
  the payment on the due date and reconciles it with the bill.
* **Deferred check / scheduled transfer**: the payments are created when
  the bill is posted, dated on each due date (future cash flow). With the
  ``insurance_management_l10n_latam_check`` bridge, own checks get one
  deferred check per installment.
* **Manual**: never paid automatically; pay the bill as usual (the
  installment becomes paid when its payable line is reconciled).
* Generating payments is idempotent: an installment is never paid twice.

Unpaid installments (phase 2)
-----------------------------

The day after the due date of an installment without payment, the daily
process marks it *Overdue*, flags the policy *With debt* (red ribbon and
*With unpaid installments* filter) and emails the template *Insurance:
overdue unpaid installment* once to the responsible and to the accounting
users to notify of the settings, each in their language; the amount only
appears for recipients allowed to see amounts. Paying it clears the debt.

Accrual (phase 2)
-----------------

* **Module accrual**: the bill goes to the prepaid insurance account; an
  accrual plan (tab *Accrual* of the policy, **Insurance ‣ Reporting ‣
  Accrual plan**) spreads its amount over the months of the validity (from
  the endorsement effective date for endorsements). The lines can be edited
  until posted. The scheduled action *Insurance: monthly accrual* posts one
  entry per policy and month (expense / prepaid insurance, with the
  analytic distribution) in the accrual journal; a closed period is posted
  on its first open day. A cancellation moves the months still to accrue to
  the cancellation month. Credit notes accrue negatively.
* **Enterprise deferred expenses** (bridge module): the bill line keeps the
  expense account and carries the validity as deferral dates.
* **No accrual**: the bill goes straight to expense.

Foreign currency (phase 2)
--------------------------

Policies, installments and bills can be in a foreign currency. Accrual is
in company currency at the rate of the bill; payments in another currency
generate the exchange difference when reconciled. Reports show the amounts
in company currency and in the original currency.

Initial load and import (phase 2)
---------------------------------

* A **running policy** (tab *Accounting*, *Initial load*) continues from a
  given installment (e.g. 4 of 12): the previous installments are created as
  historical (paid, without payments nor entries), as are those due before
  the go-live date. Its bill does not accrue again: **Generate initial
  accrual** spreads the *amount still to accrue at go-live* from the go-live
  month to the end date.
* The insurance settings compare the sum of the amounts still to accrue of
  the running policies with the opening balance of the prepaid insurance
  account before the go-live date, and show the difference.
* **Insurance ‣ Configuration ‣ Import running policies** loads policies,
  insured objects and, optionally, uneven installment amounts from an Excel
  template. Each row is processed in its own savepoint (errors are shown
  per row and the file can be read again after fixing it); policies already
  imported (same number, insurer and start date) are never changed. Large
  files are processed in batches by the scheduled action *Insurance: policy
  import*.

Reports (phase 2)
-----------------

* **Installments per month** (pivot and graph, in company currency).
* **Cost by branch and insurer**: premiums billed (net of taxes, credit
  notes deducted) per branch, insurer, policy and month, in company
  currency and in the original currency.
* The *Policy sheet* PDF now lists the endorsements and the installments.

What comes next
---------------

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
#. Accounting setup (phase 2), by an accounting administrator in
   **Insurance ‣ Configuration ‣ Settings**, section *Accounting*:

   * *Insurance product*: a service product with the purchase taxes and the
     expense account of the premiums.
   * *Billing mode* and *Accrual method* (defaults of new policies).
   * For the module accrual: the *Prepaid insurance account* (current
     asset) and the *Accrual journal* (miscellaneous).
   * *Go-live date*, for the initial load of running policies; the section
     then shows the opening balance control.
#. Create the payment modes in **Insurance ‣ Configuration ‣ Payment modes**
   (journal, payment method with its outstanding payments account, and
   whether payments are posted or left as drafts) and choose the default one
   and the *accounting users to notify* of unpaid installments in the
   settings, section *Payments*.
#. Optionally, set a product, an expense account, an analytic distribution
   and a billing mode per branch (tab *Accounting* of the branch).

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
* To change a confirmed policy (add or remove objects, change sums insured,
  coverages or data, extend or cancel it), click **New endorsement**, choose
  the type, the effective date and the affected objects, and confirm it.
  Removed objects stay listed as history.
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

Installments, bills and payments
--------------------------------

* On a confirmed policy, click **Generate installments**, check the number,
  first due date, total and payment mode, and generate. Adjust any amount or
  date in the *Installments* tab until the difference is zero.
* Click **Create bill**, complete the insurer's document data (date, number)
  and post it. Automatic debits are paid by the daily process on each due
  date (or right away with **Generate payments** once due); deferred checks
  and scheduled transfers get their payments when the bill is posted (drafts
  to review if so configured).
* For an endorsement with additional premium, use **Generate installments**
  and **Create bill** on the endorsement; for a refund, **Create credit
  note**.
* **Insurance ‣ Policies ‣ Installments** and the *With unpaid installments*
  filter of the policies show what is due and what is overdue.

Initial load
------------

* Set the go-live date in the settings, then either load each running
  policy by hand (mark *Running policy* and the installment it continues
  from; the amount still to accrue is suggested from the installments that
  follow; generate the installments and the initial accrual) or use **Insurance ‣ Configuration ‣ Import running policies**:
  download the template, fill it in, upload it, click **Read file** and
  **Process now**. Rows with errors show their message; fix the file, upload
  it again and read it: only the failed rows are replaced.
* Marking a policy as running, or changing the installment it continues
  from, after generating the installments updates them on save (historical
  or not); billed or paid installments never change. The initial accrual
  can be generated again until a month is accrued.
* Post the opening entry (prepaid insurance balance) and check that the
  *Opening difference* of the settings is zero. Link the opening bills of
  the insurers to their policies from the bill (*Insurance policy* field).

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
