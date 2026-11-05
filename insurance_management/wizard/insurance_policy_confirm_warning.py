from odoo import fields, models


class InsurancePolicyConfirmWarning(models.TransientModel):
    """Warning shown by the Confirm button when the premium and/or the total
    premium of the policies is zero: once confirmed they only change through
    an endorsement. The user can go back or confirm anyway."""

    _name = "insurance.policy.confirm.warning"
    _description = "Confirm policies with a premium at zero"

    policy_ids = fields.Many2many(comodel_name="insurance.policy", string="Policies", readonly=True)
    zero_policy_ids = fields.Many2many(
        comodel_name="insurance.policy",
        string="Policies with a premium at zero",
        compute="_compute_zero_policy_ids",
    )

    def _compute_zero_policy_ids(self):
        for wizard in self:
            wizard.zero_policy_ids = wizard.policy_ids._get_zero_amount_policies()

    def action_confirm(self):
        """Confirm anyway (without asking again)."""
        self.ensure_one()
        # The context of the Confirm button reaches this dialog: drop its key
        # or confirming would just open this warning again.
        self.policy_ids.with_context(insurance_check_amounts=False).action_confirm()
        return {"type": "ir.actions.act_window_close"}
