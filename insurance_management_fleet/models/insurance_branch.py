from odoo import fields, models


class InsuranceBranch(models.Model):
    _inherit = "insurance.branch"

    requires_fleet_vehicle = fields.Boolean(
        string="Requires fleet vehicle",
        tracking=True,
        help="Every insured object of the policies of this branch must be "
        "linked to a vehicle of the Fleet app to confirm the policy (or the "
        "endorsement that adds it).",
    )
