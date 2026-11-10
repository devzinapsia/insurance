from odoo import Command, api, fields, models
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
    "default_payment_mode_id": "insurance_default_payment_mode_id",
    "unpaid_notify_user_ids": "insurance_unpaid_notify_user_ids",
    "product_id": "insurance_product_id",
    "prepaid_account_id": "insurance_prepaid_account_id",
    "accrual_journal_id": "insurance_accrual_journal_id",
    "accrual_method": "insurance_accrual_method",
    "billing_mode": "insurance_billing_mode",
    "go_live_date": "insurance_go_live_date",
    "opening_account_id": "insurance_opening_account_id",
    "opening_journal_id": "insurance_opening_journal_id",
}
ACCOUNTING_GROUP = "account.group_account_manager"
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
    default_payment_mode_id = fields.Many2one(
        comodel_name="insurance.payment.mode",
        string="Default payment mode",
        domain="[('company_id', '=', company_id)]",
    )
    unpaid_notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_settings_unpaid_user_rel",
        column1="settings_id",
        column2="user_id",
        string="Accounting users to notify",
        domain=[("share", "=", False)],
    )
    # Accounting setup: only for accounting administrators.
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Insurance product",
        domain="[('type', '=', 'service'), ('purchase_ok', '=', True)]",
        groups=ACCOUNTING_GROUP,
    )
    prepaid_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Prepaid insurance account",
        domain="[('account_type', 'in', ('asset_prepayments', 'asset_current', 'asset_non_current'))]",
        groups=ACCOUNTING_GROUP,
    )
    accrual_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Accrual journal",
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        groups=ACCOUNTING_GROUP,
    )
    accrual_method = fields.Selection(
        selection=[("module", "Module accrual"), ("none", "No accrual (direct expense)")],
        string="Accrual method",
        groups=ACCOUNTING_GROUP,
    )
    billing_mode = fields.Selection(
        selection=[("policy", "One bill per policy"), ("installment", "One bill per installment")],
        string="Billing mode",
        groups=ACCOUNTING_GROUP,
    )
    go_live_date = fields.Date(string="Go-live date", groups=ACCOUNTING_GROUP)
    opening_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Opening transitory account",
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'off_balance'))]",
        groups=ACCOUNTING_GROUP,
    )
    opening_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Opening debt journal",
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        groups=ACCOUNTING_GROUP,
    )
    # Initial load control (section 8.7): read only, never blocks.
    opening_unaccrued_total = fields.Monetary(
        string="Still to accrue in running policies",
        currency_field="company_currency_id",
        compute="_compute_opening_control",
        groups=ACCOUNTING_GROUP,
        help="Sum of the amounts still to accrue informed on the running policies.",
    )
    opening_prepaid_balance = fields.Monetary(
        string="Opening balance of prepaid insurance",
        currency_field="company_currency_id",
        compute="_compute_opening_control",
        groups=ACCOUNTING_GROUP,
        help="Posted balance of the prepaid insurance account before the go-live date.",
    )
    opening_difference = fields.Monetary(
        string="Opening difference",
        currency_field="company_currency_id",
        compute="_compute_opening_control",
        groups=ACCOUNTING_GROUP,
        help="It must be zero: otherwise the opening entry or the amounts informed on the running policies are wrong.",
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
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
    @api.depends("company_id", "go_live_date", "prepaid_account_id")
    def _compute_opening_control(self):
        for settings in self:
            company = settings.company_id
            go_live = settings.go_live_date
            account = settings.prepaid_account_id
            unaccrued = sum(
                self.env["insurance.policy"].sudo().search(
                    [("company_id", "=", company.id), ("in_progress", "=", True), ("state", "!=", "cancelled")]
                ).mapped("unaccrued_amount")
            )
            balance = 0.0
            if go_live and account:
                groups = self.env["account.move.line"].sudo()._read_group(
                    [
                        ("company_id", "=", company.id),
                        ("account_id", "=", account.id),
                        ("parent_state", "=", "posted"),
                        ("date", "<", go_live),
                    ],
                    aggregates=["balance:sum"],
                )
                balance = groups[0][0] if groups else 0.0
            settings.opening_unaccrued_total = unaccrued
            settings.opening_prepaid_balance = balance
            settings.opening_difference = balance - unaccrued

    def _to_form_value(self, field, value):
        """Company value as expected by default_get for ``field``."""
        if field.type == "many2many":
            return [Command.set(value.ids)]
        if field.type == "many2one":
            return value.id
        return value

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
            if name in fields_list and self._has_field_access(self._fields[name], "read"):
                values[name] = self._to_form_value(self._fields[name], company[company_field])
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
            # Accounting fields are only saved by users allowed to see them.
            if not self._has_field_access(self._fields[name], "read"):
                continue
            value = self[name]
            if self._fields[name].type == "many2many":
                value = [fields.Command.set(value.ids)]
            elif self._fields[name].type == "many2one":
                value = value.id
            company_values[company_field] = value
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

    def action_open_payment_modes(self):
        return self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_payment_mode_action")

    def action_open_templates(self):
        name = self.env._("Insurance email templates")
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "mail.template",
            "view_mode": "list,form",
            "domain": [("model", "=", "insurance.policy")],
            "context": {"default_model": "insurance.policy"},
        }
