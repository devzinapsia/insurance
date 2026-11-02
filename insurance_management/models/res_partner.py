from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_insurer = fields.Boolean(
        string="Is an insurer",
        index=True,
        help="Mark this contact as an insurance company, so it can be selected "
        "as the insurer of a policy.",
    )
    is_insurance_producer = fields.Boolean(
        string="Is an insurance producer",
        index=True,
        help="Mark this contact as an insurance producer (broker), so it can "
        "be selected as the producer of a policy.",
    )
    insurance_policy_count = fields.Integer(
        string="Policies in force",
        compute="_compute_insurance_policy_count",
        groups="insurance_management.group_insurance_user",
    )

    def _get_insurance_policy_domain(self):
        self.ensure_one()
        return ["|", ("insurer_id", "=", self.id), ("producer_id", "=", self.id)]

    def _compute_insurance_policy_count(self):
        Policy = self.env["insurance.policy"]
        for partner in self:
            if not partner.id or not (partner.is_insurer or partner.is_insurance_producer):
                partner.insurance_policy_count = 0
                continue
            partner.insurance_policy_count = Policy.search_count(
                [("state", "in", ("in_force", "expiring"))]
                + partner._get_insurance_policy_domain()
            )

    def action_view_insurance_policies(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "insurance_management.insurance_policy_action"
        )
        action["domain"] = self._get_insurance_policy_domain()
        action["context"] = {"search_default_in_force": 1}
        return action
