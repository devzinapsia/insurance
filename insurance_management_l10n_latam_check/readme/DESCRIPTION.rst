Bridge between **Gestión de seguros** (``insurance_management``) and the
checks of the Latin American localization (``l10n_latam_check``). It installs
automatically when both modules are present.

Installments paid with a **deferred check** payment mode whose payment method
is *Own checks* get a payment with one own check for the installment amount,
payable on the installment due date. The payments are created when the bill
is posted, as drafts to review, so the treasurer only fills in the check
number and posts them.
