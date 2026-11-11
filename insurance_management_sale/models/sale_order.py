from odoo import fields, models

INSURANCE_GROUP = "insurance_management.group_insurance_user"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    insurance_surety_ids = fields.One2many(
        comodel_name="insurance.policy",
        inverse_name="surety_sale_order_id",
        string="Surety bonds",
        groups=INSURANCE_GROUP,
    )
    insurance_surety_count = fields.Integer(
        string="Surety bond count", compute="_compute_insurance_surety_count", groups=INSURANCE_GROUP
    )

    def _compute_insurance_surety_count(self):
        for record in self:
            record.insurance_surety_count = len(
                record.sudo().insurance_surety_ids.filtered(lambda p: not p.renewed_by_id and p.state != "draft")
            )

    def action_view_insurance_sureties(self):
        """Surety bonds guaranteeing this sale order (the last policy of
        each renewal chain)."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_policy_surety_action")
        action["domain"] = [("surety_sale_order_id", "=", self.id), ("renewed_by_id", "=", False), ("state", "!=", "draft")]
        action["context"] = {}
        return action
