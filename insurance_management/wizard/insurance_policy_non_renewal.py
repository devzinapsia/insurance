from odoo import api, fields, models


class InsurancePolicyNonRenewal(models.TransientModel):
    _name = "insurance.policy.non.renewal"
    _description = "Do not renew a policy"

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        readonly=True,
    )
    producer_id = fields.Many2one(related="policy_id.producer_id")
    reason = fields.Text(string="Reason", required=True)
    send_mode = fields.Selection(related="policy_id.non_renewal_send_mode")
    non_renewal_days = fields.Integer(related="policy_id.non_renewal_days")
    send_instruction = fields.Boolean(
        string="Send the instruction to the producer",
        compute="_compute_send_instruction",
        store=True,
        readonly=False,
        help="Email the non-renewal instruction to the producer now. It is "
        "kept in the policy chatter and the sending date is recorded.",
    )
    cc_insurer = fields.Boolean(string="Copy the insurer")
    cc_responsible = fields.Boolean(string="Copy the responsible", default=True)

    @api.depends("policy_id")
    def _compute_send_instruction(self):
        # Manual mode: send now by default. Automatic mode: the daily process
        # sends it the configured days before the end date.
        for wizard in self:
            wizard.send_instruction = wizard.policy_id.non_renewal_send_mode != "automatic"

    def action_confirm(self):
        self.ensure_one()
        self.policy_id._mark_non_renewal(self.reason)
        if self.send_instruction:
            self.policy_id._send_non_renewal_instruction(
                cc_insurer=self.cc_insurer,
                cc_responsible=self.cc_responsible,
            )
        return {"type": "ir.actions.act_window_close"}
