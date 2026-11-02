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
