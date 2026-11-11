from odoo import api, fields, models
from odoo.exceptions import UserError

from .insurance_policy_object import normalize_plate


class InsuranceEndorsementLine(models.Model):
    _inherit = "insurance.endorsement.line"

    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Fleet vehicle",
        help="Vehicle of the Fleet app added to the policy by this line.",
    )

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        for line in self.filtered("vehicle_id"):
            vehicle = line.vehicle_id
            line.license_plate = vehicle.license_plate or line.license_plate
            line.chassis_number = vehicle.vin_sn or line.chassis_number
            if not line.name:
                line.name = vehicle.display_name

    def _prepare_object_vals(self):
        vals = super()._prepare_object_vals()
        vals["vehicle_id"] = self.sudo().vehicle_id.id
        return vals

    def _find_fleet_vehicle(self):
        """The one active vehicle the new object would be linked to by plate
        or chassis (empty when there is none or several)."""
        self.ensure_one()
        company = self.endorsement_id.policy_id.company_id
        plates, chassis = self.env["insurance.policy.object"]._get_vehicle_index(company)
        matches = plates.get(normalize_plate(self.license_plate)) if self.license_plate else None
        if not matches and self.chassis_number:
            matches = chassis.get(normalize_plate(self.chassis_number))
        active = (matches or self.env["fleet.vehicle"]).filtered("active")
        return active if len(active) == 1 else self.env["fleet.vehicle"]


class InsuranceEndorsement(models.Model):
    _inherit = "insurance.endorsement"

    def _check_can_confirm(self):
        super()._check_can_confirm()
        branch = self.policy_id.branch_id
        if branch.requires_fleet_vehicle:
            missing = self.line_ids.filtered(
                lambda l: l.operation == "add" and not l.vehicle_id and not l._find_fleet_vehicle()
            )
            if missing:
                raise UserError(
                    self.env._(
                        "Branch %(branch)s requires a fleet vehicle on every insured object: choose the vehicle of %(objects)s.",
                        branch=branch.display_name,
                        objects=", ".join(missing.mapped("name")),
                    )
                )
