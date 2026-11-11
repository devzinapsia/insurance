from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InsuranceClaim(models.Model):
    _inherit = "insurance.claim"

    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Fleet vehicle",
        compute="_compute_vehicle_id",
        store=True,
        readonly=False,
        index="btree_not_null",
        help="Vehicle affected. Choosing it proposes the policy and the insured object covering it on the date of occurrence.",
    )

    @api.depends("object_id.vehicle_id")
    def _compute_vehicle_id(self):
        for claim in self:
            if claim.object_id:
                claim.vehicle_id = claim.object_id.sudo().vehicle_id

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        if self.vehicle_id and self.object_id.vehicle_id != self.vehicle_id:
            insured = self.vehicle_id._get_insurance_object(self.date_occurred)
            if insured:
                self.policy_id = insured.policy_id
                self.object_id = insured

    @api.constrains("vehicle_id", "object_id")
    def _check_vehicle(self):
        for claim in self:
            if claim.vehicle_id and claim.object_id.vehicle_id and claim.object_id.vehicle_id != claim.vehicle_id:
                raise ValidationError(self.env._("The vehicle of the claim must be the one of the affected object."))
