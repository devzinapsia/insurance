from odoo import fields, models


class InsurancePolicyObjectExclude(models.TransientModel):
    _name = "insurance.policy.object.exclude"
    _description = "Remove insured object"

    object_id = fields.Many2one(
        comodel_name="insurance.policy.object",
        string="Insured object",
        required=True,
        readonly=True,
    )
    date_end = fields.Date(
        string="Removed on",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    reason = fields.Char(string="Reason", required=True)

    def action_confirm(self):
        self.ensure_one()
        self.object_id._exclude(self.date_end, self.reason)
        return {"type": "ir.actions.act_window_close"}
