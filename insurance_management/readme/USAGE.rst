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
