from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InsuranceClaim(models.Model):
    _inherit = "insurance.claim"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Employee",
        compute="_compute_employee_id",
        store=True,
        readonly=False,
        index="btree_not_null",
        help="Employee affected. Choosing it proposes the policy and the insured object covering them on the date of occurrence.",
    )

    @api.depends("object_id.employee_id")
    def _compute_employee_id(self):
        for claim in self:
            if claim.object_id:
                claim.employee_id = claim.object_id.sudo().employee_id

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id and self.object_id.employee_id != self.employee_id:
            insured = self.employee_id._get_insurance_object(self.date_occurred)
            if insured:
                self.policy_id = insured.policy_id
                self.object_id = insured

    @api.constrains("employee_id", "object_id")
    def _check_employee(self):
        for claim in self:
            if claim.employee_id and claim.object_id.employee_id and claim.object_id.employee_id != claim.employee_id:
                raise ValidationError(self.env._("The employee of the claim must be the one of the affected object."))
