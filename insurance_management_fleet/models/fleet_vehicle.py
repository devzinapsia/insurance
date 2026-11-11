from odoo import api, fields, models
from odoo.fields import Domain

INSURANCE_GROUP = "insurance_management.group_insurance_user"


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    insurance_object_ids = fields.One2many(
        comodel_name="insurance.policy.object",
        inverse_name="vehicle_id",
        string="Insurance lines",
        groups=INSURANCE_GROUP,
    )
    insurance_policy_count = fields.Integer(
        string="Insurance policies", compute="_compute_insurance", groups=INSURANCE_GROUP
    )
    insurance_claim_count = fields.Integer(string="Insurance claims", compute="_compute_insurance", groups=INSURANCE_GROUP)
    insurance_policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Insurance policy in force",
        compute="_compute_insurance",
        groups=INSURANCE_GROUP,
        help="Policy covering the vehicle today.",
    )
    insured_today = fields.Boolean(
        string="Insured today",
        compute="_compute_insurance",
        search="_search_insured_today",
        groups=INSURANCE_GROUP,
        help="An active insured object of a policy covering today is linked to the vehicle.",
    )

    def _get_covering_objects(self):
        self.ensure_one()
        return self.sudo().insurance_object_ids.filtered(lambda o: o.state == "active" and o.policy_id.covered_today)

    @api.depends_context("insurance_today")
    def _compute_insurance(self):
        for vehicle in self:
            objects = vehicle.sudo().insurance_object_ids
            covering = vehicle._get_covering_objects()
            vehicle.insurance_policy_count = len(objects.policy_id)
            vehicle.insurance_claim_count = len(objects.claim_ids)
            vehicle.insurance_policy_id = covering[:1].policy_id
            vehicle.insured_today = bool(covering)

    def _search_insured_today(self, operator, value):
        if operator != "in":
            return NotImplemented
        insured = Domain(
            "insurance_object_ids",
            "any",
            [("state", "=", "active"), ("policy_id.covered_today", "=", True)],
        )
        if True in value and False in value:
            return Domain.TRUE
        return insured if True in value else ~insured

    def _get_insurance_object(self, date):
        """Insured object of the vehicle covering ``date`` (the latest one
        otherwise), to propose it on a new claim."""
        self.ensure_one()
        objects = self.sudo().insurance_object_ids.filtered(lambda o: o.policy_id.state != "draft")
        if date:
            covering = objects.filtered(
                lambda o: o.policy_id.date_from <= date <= o.policy_id.date_to
                and (not o.date_start or o.date_start <= date)
                and (not o.date_end or o.date_end >= date)
            )
            if covering:
                return covering.sorted(lambda o: o.policy_id.date_from, reverse=True)[:1]
        return objects.sorted(lambda o: o.policy_id.date_from, reverse=True)[:1]

    def action_view_insurance_policies(self):
        """Every policy the vehicle is (or was) insured in, newest first."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_policy_action")
        action["domain"] = [("object_ids.vehicle_id", "=", self.id)]
        action["context"] = {}
        action["view_mode"] = "list,kanban,form"
        action["views"] = [(False, "list"), (False, "kanban"), (False, "form")]
        return action

    def action_view_insurance_claims(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_claim_action")
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action
