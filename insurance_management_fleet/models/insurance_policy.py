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

    def action_open_vehicle_link(self):
        """Link the insured objects of a confirmed vehicle policy to their
        fleet vehicle (in draft they are edited on the policy itself)."""
        self.ensure_one()
        if self.object_type != "vehicle" or self.state == "draft":
            raise UserError(self.env._("Fleet vehicles are linked here only on confirmed policies of a vehicle branch."))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Link fleet vehicles"),
            "res_model": "insurance.policy.vehicle.link",
            "view_mode": "form",
            "target": "new",
            "context": {"default_policy_id": self.id},
        }
