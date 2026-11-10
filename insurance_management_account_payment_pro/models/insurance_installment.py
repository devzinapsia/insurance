from odoo import fields, models


class InsuranceInstallment(models.Model):
    _inherit = "insurance.installment"

    def _get_payment_values(self):
        """The payment pays the installment line of the bill only.

        account_payment_pro fills the debts of a new payment with every open
        payable line of the insurer and, when posted, reconciles the oldest
        ones first: the installment would stay unpaid while another bill is
        paid. Setting the debts at creation keeps the payment referencing the
        bill it pays, as when it is registered from the bill."""
        vals = super()._get_payment_values()
        if self.move_line_id:
            vals["to_pay_move_line_ids"] = [fields.Command.set(self.move_line_id.ids)]
        return vals

    def _set_payment_debt(self):
        """Debts of the draft payments of ``self``: only their installment line."""
        for installment in self.filtered(lambda i: i.payment_id.state == "draft" and i.move_line_id):
            installment.payment_id.to_pay_move_line_ids = [fields.Command.set(installment.move_line_id.ids)]
