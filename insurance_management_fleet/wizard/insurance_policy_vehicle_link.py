from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.insurance_management.models.insurance_policy_object import MASTER_LINK_CTX


class InsurancePolicyVehicleLink(models.TransientModel):
    """Link the insured objects of a confirmed vehicle policy to their fleet
    vehicle by hand (the objects themselves only change by endorsement; the
    link to the master record does not change the insured contract)."""

    _name = "insurance.policy.vehicle.link"
    _description = "Link insured objects to fleet vehicles"

    policy_id = fields.Many2one(comodel_name="insurance.policy", string="Policy", required=True, readonly=True)
    company_id = fields.Many2one(related="policy_id.company_id")
    line_ids = fields.One2many(
        comodel_name="insurance.policy.vehicle.link.line",
        inverse_name="wizard_id",
        string="Insured objects",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        policy = self.env["insurance.policy"].browse(values.get("policy_id") or self.env.context.get("default_policy_id"))
        if policy and "line_ids" in fields_list:
            values["line_ids"] = [
                Command.create({"object_id": obj.id, "vehicle_id": obj.vehicle_id.id})
                for obj in policy.object_ids.sorted(lambda o: (o.state != "active", o.sequence, o.id))
            ]
        return values

    def action_confirm(self):
        self.ensure_one()
        policy = self.policy_id
        policy.check_access("write")
        changes = []
        for line in self.line_ids.filtered(lambda l: l.object_id.vehicle_id != l.vehicle_id):
            old = line.object_id.vehicle_id
            line.object_id.with_context(**{MASTER_LINK_CTX: True}).vehicle_id = line.vehicle_id
            changes.append((line.object_id.name, old.display_name or "-", line.vehicle_id.display_name or "-"))
        if changes:
            body = Markup("%s<ul>%s</ul>") % (
                self.env._("Fleet vehicles linked by hand:"),
                Markup("").join(Markup("<li>%s: %s → %s</li>") % change for change in changes),
            )
            policy._message_log(body=body)
        return {"type": "ir.actions.act_window_close"}


class InsurancePolicyVehicleLinkLine(models.TransientModel):
    _name = "insurance.policy.vehicle.link.line"
    _description = "Insured object to link to a fleet vehicle"

    wizard_id = fields.Many2one(comodel_name="insurance.policy.vehicle.link", required=True, ondelete="cascade")
    object_id = fields.Many2one(comodel_name="insurance.policy.object", string="Insured object", required=True, readonly=True)
    name = fields.Char(related="object_id.name")
    license_plate = fields.Char(related="object_id.license_plate")
    chassis_number = fields.Char(related="object_id.chassis_number")
    object_state = fields.Selection(related="object_id.state", string="Status")
    company_id = fields.Many2one(related="object_id.company_id")
    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Fleet vehicle",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )
