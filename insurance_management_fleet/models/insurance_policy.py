from odoo import models
from odoo.exceptions import UserError


class InsurancePolicy(models.Model):
    _inherit = "insurance.policy"

    def _check_can_confirm(self):
        super()._check_can_confirm()
        if self.branch_id.requires_fleet_vehicle:
            missing = self.object_ids.filtered(lambda o: o.state == "active" and not o.vehicle_id)
            if missing:
                raise UserError(
                    self.env._(
                        "Branch %(branch)s requires a fleet vehicle on every insured object: link %(objects)s to its vehicle.",
                        branch=self.branch_id.display_name,
                        objects=", ".join(missing.mapped("name")),
                    )
                )
