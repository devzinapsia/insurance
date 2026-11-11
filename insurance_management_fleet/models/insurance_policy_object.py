import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.insurance_management.models.insurance_policy_object import MASTER_LINK_CTX


def normalize_plate(value):
    """License plate / chassis as compared: uppercase, without spaces,
    dashes nor dots ("ab-123 cd" == "AB123CD")."""
    return re.sub(r"[\s\-.]", "", value or "").upper()


class InsurancePolicyObject(models.Model):
    _inherit = "insurance.policy.object"

    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Fleet vehicle",
        index="btree_not_null",
        check_company=True,
        help="Vehicle of the Fleet app insured by this line. Its insurance "
        "history and claims are shown on the vehicle. Linked automatically by "
        "license plate (or chassis number) when it matches one vehicle only.",
    )

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        for record in self.filtered("vehicle_id"):
            vehicle = record.vehicle_id
            record.license_plate = vehicle.license_plate or record.license_plate
            record.chassis_number = vehicle.vin_sn or record.chassis_number
            if not record.name:
                record.name = vehicle.display_name

    @api.constrains("vehicle_id", "policy_id")
    def _check_vehicle_branch(self):
        for record in self.filtered("vehicle_id"):
            if record.policy_id.branch_id.object_type != "vehicle":
                raise ValidationError(
                    self.env._("Only policies of a branch of type Vehicle can insure fleet vehicles.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered(
            lambda r: not r.vehicle_id and r.policy_id.branch_id.object_type == "vehicle"
        )._link_fleet_vehicles()
        return records

    def _prepare_renewal_vals(self):
        vals = super()._prepare_renewal_vals()
        vals["vehicle_id"] = self.sudo().vehicle_id.id
        return vals

    def _get_vehicle_index(self, companies):
        """Normalized plate and chassis -> vehicles of ``companies`` (and the
        shared ones), archived included so they can be reported."""
        vehicles = self.env["fleet.vehicle"].sudo().with_context(active_test=False).search(
            ["|", ("company_id", "=", False), ("company_id", "in", companies.ids)]
        )
        plates, chassis = {}, {}
        for vehicle in vehicles:
            if vehicle.license_plate:
                plates.setdefault(normalize_plate(vehicle.license_plate), self.env["fleet.vehicle"])
                plates[normalize_plate(vehicle.license_plate)] |= vehicle
            if vehicle.vin_sn:
                chassis.setdefault(normalize_plate(vehicle.vin_sn), self.env["fleet.vehicle"])
                chassis[normalize_plate(vehicle.vin_sn)] |= vehicle
        return plates, chassis

    def _link_fleet_vehicles(self, report=False):
        """Link each object to the one active vehicle of its company with the
        same license plate or, without a plate match, the same chassis
        number. Several or only archived matches are skipped: never guessed.

        :return: (linked objects, objects left without vehicle)
        """
        linked = skipped = self.browse()
        records = self.sudo().filtered(lambda r: r.license_plate or r.chassis_number)
        if not records:
            return linked, skipped
        plates, chassis = self._get_vehicle_index(records.company_id)
        for record in records:
            matches = self.env["fleet.vehicle"]
            if record.license_plate:
                matches = plates.get(normalize_plate(record.license_plate), matches)
            if not matches and record.chassis_number:
                matches = chassis.get(normalize_plate(record.chassis_number), matches)
            matches = matches.filtered(lambda v: not v.company_id or v.company_id == record.company_id)
            active = matches.filtered("active")
            if len(active) == 1:
                record.with_context(**{MASTER_LINK_CTX: True}).vehicle_id = active
                linked |= record
                continue
            skipped |= record
            if report and matches:
                record.policy_id.with_context(lang=record.policy_id._get_chatter_lang())._message_log(
                    body=self.env._(
                        "Insured object %(object)s was not linked to a fleet vehicle: %(reason)s",
                        object=record.name,
                        reason=self.env._("several vehicles match its plate or chassis.")
                        if len(active) > 1
                        else self.env._("the only matching vehicle is archived."),
                    )
                )
        return linked, skipped

    @api.model
    def _get_master_link_fields(self):
        return super()._get_master_link_fields() | {"vehicle_id"}
