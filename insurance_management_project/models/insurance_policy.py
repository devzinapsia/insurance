from odoo import fields, models


class InsurancePolicy(models.Model):
    _inherit = "insurance.policy"

    surety_project_id = fields.Many2one(
        comodel_name="project.project",
        string="Guaranteed project",
        index="btree_not_null",
        copy=False,
        groups="project.group_project_user",
        help="Project whose fulfilment the surety bond guarantees (e.g. a public work guaranteed with a performance bond).",
    )

    def _prepare_renewal_vals(self):
        vals = super()._prepare_renewal_vals()
        # Only when set: the field is restricted to its app users, and a
        # renewal created by code without sudo must not need that access.
        if self.sudo().surety_project_id:
            vals["surety_project_id"] = self.sudo().surety_project_id.id
        return vals
