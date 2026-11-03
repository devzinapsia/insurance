from odoo import fields, models


class InsuranceInstallment(models.Model):
    _inherit = "insurance.installment"

    def _get_payment_values(self):
        """Own checks: the payment carries one deferred check for the
        installment amount, payable on its due date. The check number is
        filled in by the treasurer before posting (draft payment mode)."""
        vals = super()._get_payment_values()
        if self.payment_mode_id.payment_method_line_id.code == "own_checks":
            vals["l10n_latam_new_check_ids"] = [
                fields.Command.create({"payment_date": self.due_date, "amount": vals["amount"]})
            ]
        return vals
