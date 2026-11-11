from odoo import fields, models


class InsurancePolicy(models.Model):
    _inherit = "insurance.policy"

    surety_sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Guaranteed sale order",
        index="btree_not_null",
        copy=False,
        groups="sales_team.group_sale_salesman",
        help="Sale order whose fulfilment the surety bond guarantees (e.g. a performance bond of a contract with a client).",
    )

    def _prepare_renewal_vals(self):
        vals = super()._prepare_renewal_vals()
        # Only when set: the field is restricted to its app users, and a
        # renewal created by code without sudo must not need that access.
        if self.sudo().surety_sale_order_id:
            vals["surety_sale_order_id"] = self.sudo().surety_sale_order_id.id
        return vals
