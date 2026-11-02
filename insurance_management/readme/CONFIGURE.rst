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
