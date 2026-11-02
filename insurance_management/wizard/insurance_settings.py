from odoo import api, fields, models
from odoo.exceptions import AccessError

from ..models.insurance_policy import DEFAULT_BATCH_SIZE

COMPANY_FIELDS = {
    "alert_days": "insurance_alert_days",
    "notify_user_ids": "insurance_notify_user_ids",
    "min_duration_months": "insurance_min_duration_months",
    "max_duration_months": "insurance_max_duration_months",
    "duration_check": "insurance_duration_check",
    "coverage_time": "insurance_coverage_time",
    "non_renewal_send_mode": "insurance_non_renewal_send_mode",
    "non_renewal_days": "insurance_non_renewal_days",
}
BATCH_SIZE_PARAM = "insurance_management.cron_batch_size"


class InsuranceSettings(models.TransientModel):
    """Insurance settings, editable by the insurance Administrator.

    Odoo's own Settings screen can only be saved by system administrators;
    this form lets the insurance Administrator manage the parameters of the
    current company (and the few global ones) without that right.
    """

    _name = "insurance.settings"
    _description = "Insurance settings"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    alert_days = fields.Char(string="Alert days")
    notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_settings_notify_user_rel",
        column1="settings_id",
        column2="user_id",
        string="Users to notify",
        domain=[("share", "=", False)],
    )
    min_duration_months = fields.Integer(string="Minimum policy duration (months)")
    max_duration_months = fields.Integer(string="Maximum policy duration (months)")
    duration_check = fields.Selection(
        selection=[("warning", "Warning"), ("block", "Block")],
        string="Policy duration check",
        required=True,
    )
    coverage_time = fields.Selection(
        selection=[("12", "12:00"), ("0", "0:00")],
        string="Coverage start and end time",
        required=True,
    )
    non_renewal_send_mode = fields.Selection(
        selection=[("manual", "Manual"), ("automatic", "Automatic")],
        string="Non-renewal instruction sending",
        required=True,
    )
    non_renewal_days = fields.Integer(string="Send non-renewal instruction (days before)")
    hide_costs = fields.Boolean(
        string="Hide costs from users",
        help="When checked, insurance users only see policy amounts (premiums, "
        "sums insured, deductibles) if they have the \"Insurance: see amounts\" "
        "access. Administrators always see them. Applies to all companies.",
    )
    batch_size = fields.Integer(
        string="Batch size of the daily process",
        help="Number of policies processed and committed together by the daily "
        "expiry process. Applies to all companies.",
    )

    @api.depends("company_id")
    def _compute_display_name(self):
        for settings in self:
            settings.display_name = self.env._("Insurance settings")

    @api.model
    def _check_manager(self):
        if not self.env.user.has_group("insurance_management.group_insurance_manager"):
            raise AccessError(self.env._("Only an insurance administrator can change the insurance settings."))

    @api.model
    def _get_amount_groups(self):
        return (
            self.env.ref("insurance_management.group_insurance_user"),
            self.env.ref("insurance_management.group_insurance_see_amounts"),
        )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        for name, company_field in COMPANY_FIELDS.items():
            if name in fields_list:
                value = company[company_field]
                values[name] = value.ids if isinstance(value, models.BaseModel) else value
        user_group, see_amounts = self._get_amount_groups()
        values["hide_costs"] = see_amounts not in user_group.sudo().all_implied_ids
        values["batch_size"] = int(
            self.env["ir.config_parameter"].sudo().get_param(BATCH_SIZE_PARAM, DEFAULT_BATCH_SIZE)
        )
        return values

    def action_save(self):
        self.ensure_one()
        self._check_manager()
        company_values = {}
        for name, company_field in COMPANY_FIELDS.items():
            value = self[name]
            company_values[company_field] = (
                [fields.Command.set(value.ids)] if isinstance(value, models.BaseModel) else value
            )
        self.company_id.sudo().write(company_values)
        user_group, see_amounts = self._get_amount_groups()
        if self.hide_costs:
            user_group.sudo()._remove_group(see_amounts.sudo())
        else:
            user_group.sudo()._apply_group(see_amounts.sudo())
        self.env["ir.config_parameter"].sudo().set_param(
            BATCH_SIZE_PARAM, max(self.batch_size, 1)
        )
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def action_run_expiry_process(self):
        """Run the daily expiry process now (as the scheduled action does)."""
        self._check_manager()
        self.env.ref("insurance_management.ir_cron_insurance_policy_expiry").sudo().method_direct_trigger()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("The expiry process has been run."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_open_templates(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Insurance email templates"),
            "res_model": "mail.template",
            "view_mode": "list,form",
            "domain": [("model", "=", "insurance.policy")],
            "context": {"default_model": "insurance.policy"},
        }
