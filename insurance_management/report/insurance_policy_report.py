from odoo import api, fields, models

AMOUNTS_GROUP = "insurance_management.group_insurance_see_amounts"


class ReportInsurancePolicy(models.AbstractModel):
    """Policy sheet: amounts only for users allowed to see them."""

    _name = "report.insurance_management.report_insurance_policy"
    _description = "Insurance policy sheet"

    @api.model
    def _get_report_values(self, docids, data=None):
        show_amounts = self.env.user.has_group(AMOUNTS_GROUP)
        return {
            "doc_ids": docids,
            "doc_model": "insurance.policy",
            "docs": self.env["insurance.policy"].browse(docids),
            "show_amounts": show_amounts,
        }


class ReportInsurancePolicyList(models.AbstractModel):
    """List of policies (in force), ordered by end date."""

    _name = "report.insurance_management.report_insurance_policy_list"
    _description = "Insurance policies in force list"

    @api.model
    def _get_report_values(self, docids, data=None):
        policies = self.env["insurance.policy"].browse(docids).sorted(
            lambda policy: (policy.date_to or fields.Date.today(), policy.id)
        )
        return {
            "doc_ids": docids,
            "doc_model": "insurance.policy",
            "docs": policies,
            "show_amounts": self.env.user.has_group(AMOUNTS_GROUP),
            "print_date": fields.Date.context_today(self),
        }
