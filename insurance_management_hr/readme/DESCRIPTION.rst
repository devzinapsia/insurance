Bridge between **Gestión de seguros** (``insurance_management``) and
**Employees** (``hr``). It installs automatically when both modules are
present.

* Insured objects of person branches (personal accident, life) and the
  endorsement lines adding objects get an *Employee*. Renewals and
  endorsements keep it.
* The employee form shows the *Insurance* smart button (every policy, and
  whether they are insured today) and the *Claims* button; the employee list
  and search get *Insured today*.
* Claims get the *Employee*: choosing it proposes the policy and the object
  covering them on the date of occurrence.
* Insurance users without Employees rights see the employee names through
  the public employee data.
