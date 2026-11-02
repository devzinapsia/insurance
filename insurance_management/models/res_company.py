from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .insurance_tools import format_alert_days, parse_alert_days


class ResCompany(models.Model):
    _inherit = "res.company"

    insurance_min_duration_months = fields.Integer(
        string="Minimum policy duration (months)",
        default=1,
        help="Shortest validity period accepted for an insurance policy.",
    )
    insurance_max_duration_months = fields.Integer(
        string="Maximum policy duration (months)",
        default=12,
        help="Longest validity period accepted for an insurance policy.",
    )
    insurance_duration_check = fields.Selection(
        selection=[("warning", "Warning"), ("block", "Block")],
        string="Policy duration check",
        default="block",
        required=True,
        help="What happens when a policy duration is outside the minimum and "
        "maximum: show a warning and let it be confirmed, or block it.",
    )

    insurance_coverage_time = fields.Selection(
        selection=[("12", "12:00"), ("0", "0:00")],
        string="Coverage start and end time",
        default="12",
        required=True,
        help="Time at which policies start and end, shown in the emails. "
        "12:00: the policy ends at noon of its end date. 0:00: it ends at "
        "midnight, at 0:00 of the day after its end date.",
    )

    insurance_alert_days = fields.Char(
        string="Alert days",
        default="30",
        help="Days before the policy end date on which an expiry notice is "
        "sent, as a comma-separated list (e.g. 30,15,7). A branch or a policy "
        "can set its own value, which takes precedence.",
    )
    insurance_notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_company_notify_user_rel",
        column1="company_id",
        column2="user_id",
        string="Users to notify",
        domain=[("share", "=", False)],
        help="Users notified about every policy of the company, in addition to "
        "the users of the branch, of the policy and its responsible.",
    )
    insurance_non_renewal_send_mode = fields.Selection(
        selection=[("manual", "Manual"), ("automatic", "Automatic")],
        string="Non-renewal instruction sending",
        default="manual",
        required=True,
        help="Manual: sent from the Do not renew button. Automatic: sent by "
        "the daily process the configured days before the end date, for "
        "policies marked not to renew.",
    )
    insurance_non_renewal_days = fields.Integer(
        string="Send non-renewal instruction (days before)",
        default=30,
        help="Days before the end date on which the automatic non-renewal "
        "instruction is sent.",
    )

    @api.constrains("insurance_alert_days")
    def _check_insurance_alert_days(self):
        for company in self:
            parse_alert_days(self.env, company.insurance_alert_days)

    @api.constrains("insurance_non_renewal_days")
    def _check_insurance_non_renewal_days(self):
        for company in self:
            if company.insurance_non_renewal_days < 0:
                raise ValidationError(
                    self.env._("The days before sending the non-renewal instruction cannot be negative.")
                )

    @api.constrains("insurance_min_duration_months", "insurance_max_duration_months")
    def _check_insurance_duration_limits(self):
        for company in self:
            if company.insurance_min_duration_months < 1:
                raise ValidationError(
                    self.env._("The minimum policy duration must be at least 1 month.")
                )
            if company.insurance_max_duration_months < company.insurance_min_duration_months:
                raise ValidationError(
                    self.env._(
                        "The maximum policy duration cannot be shorter than the minimum duration."
                    )
                )

    def write(self, vals):
        if "insurance_alert_days" in vals:
            vals["insurance_alert_days"] = format_alert_days(self.env, vals["insurance_alert_days"])
        return super().write(vals)
