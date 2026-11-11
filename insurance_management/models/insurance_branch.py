from odoo import api, fields, models

from .insurance_tools import format_alert_days, parse_alert_days


class InsuranceBranch(models.Model):
    """Insurance line of business (e.g. motor, fire, surety bond).

    Defines the kind of insured object and the defaults that policies of
    this branch inherit (alert thresholds, extra users to notify).
    """

    _name = "insurance.branch"
    _description = "Insurance branch"
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True, tracking=True)
    code = fields.Char(tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    object_type = fields.Selection(
        selection=[
            ("vehicle", "Vehicle"),
            ("person", "Person"),
            ("property", "Property"),
            ("contract", "Contract"),
            ("generic", "Generic"),
        ],
        string="Object type",
        required=True,
        default="generic",
        tracking=True,
        help="Kind of object insured by policies of this branch. It defines "
        "which specific fields are shown on the policy's insured objects.",
    )
    alert_days = fields.Char(
        string="Alert days",
        tracking=True,
        help="Days before the policy end date on which an expiry notice is "
        "sent, as a comma-separated list (e.g. 30,15,7). Leave empty to use "
        "the value of the insurance settings. A value set on the policy "
        "takes precedence over this one.",
    )
    notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_branch_notify_user_rel",
        column1="branch_id",
        column2="user_id",
        string="Users to notify",
        domain=[("share", "=", False)],
        help="Additional users notified about policies of this branch. They "
        "are added to the users of the insurance settings and of the policy.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        index=True,
        help="Leave empty to share this branch across all companies.",
    )
    note = fields.Html(string="Notes")
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Insurance product",
        domain="[('type', '=', 'service'), ('purchase_ok', '=', True)]",
        help="Service product of the bills of this branch. Leave empty to use "
        "the one of the insurance settings.",
    )
    expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Expense account",
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Leave empty to use the expense account of the insurance product.",
    )
    billing_mode = fields.Selection(
        selection=[("policy", "One bill per policy"), ("installment", "One bill per installment")],
        string="Billing mode",
        help="Leave empty to use the one of the insurance settings.",
    )
    claim_receivable_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Claims receivable account",
        domain="[('account_type', '=', 'asset_receivable')]",
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Leave empty to use the one of the insurance settings.",
    )
    claim_recovery_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Claims recovery account",
        domain="[('account_type', 'in', ('income', 'income_other', 'expense', 'expense_direct_cost'))]",
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Leave empty to use the one of the insurance settings.",
    )
    surety_loss_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Surety execution loss account",
        domain="[('account_type', 'in', ('expense', 'expense_other', 'expense_direct_cost'))]",
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Leave empty to use the one of the insurance settings.",
    )

    # COALESCE so that two shared branches (no company) cannot reuse a code;
    # a plain UNIQUE would treat their NULL company_id values as distinct.
    _code_company_uniq = models.UniqueIndex(
        "(code, COALESCE(company_id, 0)) WHERE code IS NOT NULL",
        "The branch code must be unique per company.",
    )

    @api.constrains("alert_days")
    def _check_alert_days(self):
        for branch in self:
            parse_alert_days(self.env, branch.alert_days)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "alert_days" in vals:
                vals["alert_days"] = format_alert_days(self.env, vals["alert_days"])
        return super().create(vals_list)

    def write(self, vals):
        if "alert_days" in vals:
            vals["alert_days"] = format_alert_days(self.env, vals["alert_days"])
        return super().write(vals)

    def get_alert_days_list(self):
        """Return this branch's thresholds as a list (largest first)."""
        self.ensure_one()
        return parse_alert_days(self.env, self.alert_days)
