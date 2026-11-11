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

    # Accounting (Fase 2, section 4.9) --------------------------------------------
    insurance_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Insurance product",
        domain="[('type', '=', 'service'), ('purchase_ok', '=', True)]",
        help="Service product used on insurance bills: its taxes and expense "
        "account are proposed on every bill (a branch can use its own product).",
    )
    insurance_prepaid_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Prepaid insurance account",
        domain="[('account_type', 'in', ('asset_prepayments', 'asset_current', 'asset_non_current'))]",
        help="Asset account where the premium waits to be accrued month by "
        "month (module accrual).",
    )
    insurance_accrual_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Accrual journal",
        domain="[('type', '=', 'general')]",
        help="Miscellaneous journal of the monthly accrual entries (module accrual).",
    )
    insurance_accrual_method = fields.Selection(
        selection=[("module", "Module accrual"), ("none", "No accrual (direct expense)")],
        string="Accrual method",
        default="module",
        required=True,
        help="Default accrual method of new policies.",
    )
    insurance_billing_mode = fields.Selection(
        selection=[("policy", "One bill per policy"), ("installment", "One bill per installment")],
        string="Billing mode",
        default="policy",
        required=True,
        help="Default billing mode of new policies (a branch can set its own).",
    )
    insurance_default_payment_mode_id = fields.Many2one(
        comodel_name="insurance.payment.mode",
        string="Default payment mode",
        help="Payment mode proposed on new policies.",
    )
    insurance_opening_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Opening transitory account",
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'off_balance'))]",
        help="Running policies billed up front: the opening debt with the "
        "insurer (installments left at go-live) is brought in with a bill on "
        "this account, against the same account in the opening entry, so it "
        "ends at zero.",
    )
    insurance_opening_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Opening debt journal",
        domain="[('type', '=', 'purchase')]",
        help="Purchase journal of the opening debt bills (e.g. one without "
        "fiscal documents). Empty: the default purchase journal.",
    )
    insurance_go_live_date = fields.Date(
        string="Go-live date",
        help="Installments due before this date are historical: they are "
        "recorded as paid, without payments nor journal entries.",
    )
    insurance_unpaid_notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_company_unpaid_notify_user_rel",
        column1="company_id",
        column2="user_id",
        string="Accounting users to notify",
        domain=[("share", "=", False)],
        help="Users (typically accounting) notified, with the responsible, when "
        "an installment is overdue and unpaid.",
    )

    # Claims and sureties (Fase 3, sections 4.9 and 8.6) --------------------------
    insurance_claim_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Claims journal",
        domain="[('type', '=', 'general')]",
        help="Miscellaneous journal of the claim entries: approval, offsets "
        "and closing differences.",
    )
    insurance_claim_receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Claims receivable account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Receivable account of the indemnities to collect from insurers "
        "(type Receivable, so the claim shows in the aging and is collected "
        "like any receivable). A branch can use its own.",
    )
    insurance_claim_recovery_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Claims recovery account",
        domain="[('account_type', 'in', ('income', 'income_other', 'expense', 'expense_direct_cost'))]",
        help="Account credited when a claim is approved (recovery of the "
        "damage). A branch can use its own.",
    )
    insurance_surety_loss_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Surety execution loss account",
        domain="[('account_type', 'in', ('expense', 'expense_other', 'expense_direct_cost'))]",
        help="Account debited when a surety bond is executed, against the debt "
        "with the insurer that pays the beneficiary. A branch can use its own.",
    )
    insurance_claim_stale_days = fields.Integer(
        string="Claims without movement (days)",
        default=30,
        help="An open claim whose status has not changed for this many days is "
        "notified to its responsible, again every this many days. Zero: never.",
    )
    insurance_surety_release_days = fields.Integer(
        string="Request the surety release (days before)",
        default=30,
        help="Days before the end of the guaranteed obligation on which the "
        "release of the surety bond is requested.",
    )
    insurance_surety_release_send_mode = fields.Selection(
        selection=[("manual", "Manual"), ("automatic", "Automatic")],
        string="Surety release request sending",
        default="manual",
        required=True,
        help="Manual: the responsible gets an activity and sends the request "
        "with the Request release button. Automatic: the daily process emails "
        "it to the beneficiary (or the producer), with a copy to the responsible.",
    )

    @api.constrains("insurance_claim_stale_days", "insurance_surety_release_days")
    def _check_insurance_claim_days(self):
        for company in self:
            if company.insurance_claim_stale_days < 0 or company.insurance_surety_release_days < 0:
                raise ValidationError(self.env._("The days of the claim and surety alerts cannot be negative."))

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
