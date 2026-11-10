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
