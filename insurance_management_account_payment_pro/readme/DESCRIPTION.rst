Bridge between **Gestión de seguros** (``insurance_management``) and adhoc's
payments (``account_payment_pro``). It installs automatically when both
modules are present.

``account_payment_pro`` fills the debts of every new vendor payment with all
the open payable lines of the partner and, when the payment is posted,
reconciles the oldest ones first. The payments created for insurance
installments (automatic debit, scheduled transfer, deferred check) would then
list every debt with the insurer and could pay another bill. With this module
the payment of an installment carries only the installment line of its bill
in *Debts*, as when the payment is registered from the bill.

When installed, the draft payments of installments already created get their
debts fixed the same way.
