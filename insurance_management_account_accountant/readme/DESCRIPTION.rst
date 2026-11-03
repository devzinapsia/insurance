Bridge between **Gestión de seguros** (``insurance_management``) and the
deferred expenses of Odoo Enterprise (``account_accountant``). It installs
automatically when both modules are present.

It adds the accrual method **Enterprise deferred expenses**: the bills created
from the policies keep the expense account on their line and carry the
validity of the policy (or of the endorsement, from its effective date) as
deferral start and end dates. Odoo Enterprise then creates the deferral
entries, so the premium is expensed month by month without the accrual plan of
the base module.
