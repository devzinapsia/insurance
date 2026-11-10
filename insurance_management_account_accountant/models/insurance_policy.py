from odoo import fields, models

from odoo.addons.insurance_management.models.insurance_policy import OPENING_DEBT_CTX

DEFERRED = [("deferred", "Enterprise deferred expenses")]


def _fallback_to_direct_expense(field_name):
    """On uninstall, policies and companies using the deferred method fall back
    to direct expense (their bills already carry their deferred entries)."""

    def fallback(records):
        records.write({field_name: "none"})

    return fallback


class InsurancePolicy(models.Model):
    _inherit = "insurance.policy"

    accrual_method = fields.Selection(
        selection_add=DEFERRED,
        ondelete={"deferred": _fallback_to_direct_expense("accrual_method")},
    )

    def _prepare_bill_line_vals(self, amount, label, date_from, date_to):
        """Enterprise deferred expenses: the bill line keeps the expense
        account and carries the validity; Enterprise creates the deferral
        entries month by month (company "deferred expense" settings)."""
        vals = super()._prepare_bill_line_vals(amount, label, date_from, date_to)
        # The opening debt bill (running policy billed up front) is not a new
        # cost: never deferred.
        if self.accrual_method == "deferred" and not self.env.context.get(OPENING_DEBT_CTX):
            go_live = self.company_id.insurance_go_live_date
            if self.in_progress and go_live and date_from < go_live:
                # Running policy (initial load): the installments billed in
                # Odoo are spread over the months left after go-live.
                date_from = go_live
            vals.update({"deferred_start_date": date_from, "deferred_end_date": date_to})
        return vals
