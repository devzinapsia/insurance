from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InsurancePolicyObject(models.Model):
    _inherit = "insurance.policy.object"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Employee",
        index="btree_not_null",
        check_company=True,
        help="Employee insured by this line (personal accident, life). The "
        "insurance history and claims are shown on the employee.",
    )

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for record in self.filtered("employee_id"):
            if not record.name:
                record.name = record.employee_id.name

    @api.constrains("employee_id", "policy_id")
    def _check_employee_branch(self):
        for record in self.filtered("employee_id"):
            if record.policy_id.branch_id.object_type != "person":
                raise ValidationError(
                    self.env._("Only policies of a branch of type Person can insure employees.")
                )

    def _prepare_renewal_vals(self):
        vals = super()._prepare_renewal_vals()
        vals["employee_id"] = self.sudo().employee_id.id
        return vals

    @api.model
    def _get_master_link_fields(self):
        return super()._get_master_link_fields() | {"employee_id"}


class InsuranceEndorsementLine(models.Model):
    _inherit = "insurance.endorsement.line"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Employee",
        help="Employee added to the policy by this line.",
    )

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for line in self.filtered("employee_id"):
            if not line.name:
                line.name = line.employee_id.name

    def _prepare_object_vals(self):
        vals = super()._prepare_object_vals()
        vals["employee_id"] = self.sudo().employee_id.id
        return vals
