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
* The vehicle form shows the *Insurance* smart button (every policy, with
  *Insured* / *Not insured* today) and the *Claims* button; the vehicle list
  and search get *Insured today* and *Without insurance in force*.
* Claims get the *Fleet vehicle*: choosing it proposes the policy and the
  object covering it on the date of occurrence.
* The dashboard shows the vehicles without insurance in force.
* Insurance users without Fleet rights can read the vehicles of the
  policies.
