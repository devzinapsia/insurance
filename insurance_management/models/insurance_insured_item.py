from odoo import fields, models


class InsuranceInsuredItem(models.Model):
    """Insurable item master: something insured that does not exist elsewhere
    in Odoo (a warehouse, a shop, a piece of equipment...).

    Policy object lines point to this master, so the item keeps its insurance
    history across renewals.
    """

    _name = "insurance.insured.item"
    _description = "Insurable item"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name, id"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    item_type = fields.Selection(
        selection=[
            ("real_estate", "Real estate"),
            ("goods", "Goods"),
            ("equipment", "Equipment"),
            ("other", "Other"),
        ],
        string="Item type",
        required=True,
        default="other",
        tracking=True,
    )
    location = fields.Char(tracking=True)
    identification = fields.Char(
        tracking=True,
        help="Serial number, cadastral reference or any other identification.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    reference_value = fields.Monetary(
        string="Reference value",
        currency_field="currency_id",
        tracking=True,
        groups="insurance_management.group_insurance_see_amounts",
        help="Approximate value of the item, as a reference for the sum insured.",
    )
    object_ids = fields.One2many(
        comodel_name="insurance.policy.object",
        inverse_name="insured_item_id",
        string="Policy objects",
    )
    note = fields.Html(string="Notes")
    policy_count = fields.Integer(string="Policy count", compute="_compute_policy_count")
    claim_count = fields.Integer(string="Claim count", compute="_compute_policy_count")

    def _compute_policy_count(self):
        for item in self:
            item.policy_count = len(item.object_ids.policy_id)
            item.claim_count = len(item.object_ids.claim_ids)

    def action_view_claims(self):
        """Every claim of the item, in all its policies."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_claim_action")
        action["domain"] = [("object_id", "in", self.object_ids.ids)]
        action["context"] = {}
        return action

    def action_view_policies(self):
        """Every policy the item is (or was) insured in."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_policy_action")
        action["domain"] = [("id", "in", self.object_ids.policy_id.ids)]
        action["context"] = {}
        action["view_mode"] = "list,kanban,form"
        action["views"] = [(False, "list"), (False, "kanban"), (False, "form")]
        return action

    def _get_object_values(self, currency):
        """Values proposed on an insured object line when this item is chosen:
        its name, and its reference value as sum insured when the policy is in
        the same currency (only for users allowed to see amounts)."""
        self.ensure_one()
        values = {"name": self.name}
        item = self.sudo()
        if (
            item.reference_value
            and (not currency or currency == item.currency_id)
            and self.env.user.has_group("insurance_management.group_insurance_see_amounts")
        ):
            values["sum_insured"] = item.reference_value
        return values
