import logging

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import date_utils, format_amount, format_date

from .insurance_endorsement import ENDORSEMENT_CTX
from .insurance_tools import format_alert_days, parse_alert_days

_logger = logging.getLogger(__name__)

AMOUNTS_GROUP = "insurance_management.group_insurance_see_amounts"
# Policies in force: they count as "in force" and get the expiry alerts.
ACTIVE_STATES = ("in_force", "expiring")
# Confirmed and not ended: contract data only change through endorsements,
# and they can be billed. "Not started" = confirmed, start date still ahead.
CONFIRMED_STATES = ("not_started", "in_force", "expiring")
# Default size of the batches of the daily process (ir.config_parameter
# insurance_management.cron_batch_size overrides it).
DEFAULT_BATCH_SIZE = 200

# States in which a policy can no longer be edited (except chatter,
# activities and the fields returned by _get_locked_writable_fields()).
LOCKED_STATES = ("expired", "renewed", "not_renewed", "cancelled")
# States that never count as "covered", whatever the dates.
UNCOVERED_STATES = ("draft", "cancelled")
# Context key allowing internal lifecycle writes (state changes, links).
LIFECYCLE_CTX = "insurance_lifecycle_write"
# Set by the Confirm button: ask before confirming policies whose premium
# and/or total premium is zero (code callers, e.g. the import, never ask).
AMOUNT_CHECK_CTX = "insurance_check_amounts"
# Contract data of a confirmed policy: only an endorsement can change them
# (RF-06; Fase 2 retired the Fase 1 transitional editing rule).
CONTRACT_FIELDS = {
    "policy_number",
    "branch_id",
    "insurer_id",
    "producer_id",
    "date_from",
    "date_to",
    "currency_id",
    "premium",
    "premium_total",
    "deductible_type",
    "deductible_amount",
    "deductible_percent",
    "coverage",
    "company_id",
    "object_ids",
}
BILLING_MODES = [("policy", "One bill per policy"), ("installment", "One bill per installment")]
ACCRUAL_METHODS = [("module", "Module accrual"), ("none", "No accrual (direct expense)")]
# Context key telling message_post which producer email is being sent, so the
# matching "sent on" date is stamped on the policy.
MAIL_KIND_CTX = "insurance_mail_kind"
MAIL_KIND_FIELDS = {
    "non_renewal": "non_renewal_sent_date",
    "renewal_request": "renewal_request_sent_date",
}


class InsurancePolicy(models.Model):
    _name = "insurance.policy"
    _description = "Insurance policy"
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]
    _order = "date_to desc, id desc"
    _rec_names_search = ["name", "policy_number"]
    _check_company_auto = True

    name = fields.Char(
        string="Reference",
        required=True,
        readonly=True,
        copy=False,
        index="trigram",
        default=lambda self: self.env._("New"),
    )
    policy_number = fields.Char(
        string="Policy number",
        copy=False,
        index=True,
        tracking=True,
        help="Number assigned by the insurer. Required to confirm the policy.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("not_started", "Not started"),
            ("in_force", "In force"),
            ("expiring", "Expiring"),
            ("expired", "Expired"),
            ("renewed", "Renewed"),
            ("not_renewed", "Not renewed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        required=True,
        readonly=True,
        copy=False,
        index=True,
        default="draft",
        tracking=True,
        group_expand=True,
    )
    branch_id = fields.Many2one(
        comodel_name="insurance.branch",
        string="Branch",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
    )
    object_type = fields.Selection(related="branch_id.object_type")
    insurer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Insurer",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        domain="[('is_insurer', '=', True)]",
        help="Only contacts marked \"Is an insurer\" are listed (contact form, "
        "Sales & Purchase tab). A contact created from here is marked "
        "automatically.",
    )
    producer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Producer",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        domain="[('is_insurance_producer', '=', True)]",
        help="Only contacts marked \"Is an insurance producer\" are listed "
        "(contact form, Sales & Purchase tab). A contact created from here is "
        "marked automatically.",
    )
    date_from = fields.Date(string="Valid from", tracking=True, copy=False)
    date_to = fields.Date(
        string="Valid to",
        tracking=True,
        copy=False,
        index=True,
        help="Last day covered by the policy (inclusive).",
    )
    duration_months = fields.Integer(
        string="Duration (months)",
        compute="_compute_duration",
        store=True,
        help="Whole months between the start date and the day after the end date.",
    )
    duration_days = fields.Integer(
        string="Extra days",
        compute="_compute_duration",
        store=True,
        help="Days left over after the whole months of the duration.",
    )
    duration_warning = fields.Char(
        string="Duration warning",
        compute="_compute_duration_warning",
    )
    renewal_type = fields.Selection(
        selection=[
            ("undefined", "To be defined"),
            ("renew", "Renew"),
            ("no_renew", "Do not renew"),
        ],
        string="Renewal type",
        required=True,
        default="undefined",
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        required=True,
        index=True,
        tracking=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
        help="Receives the expiry alerts and activities of this policy.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        required=True,
        tracking=True,
        default=lambda self: self.env.company.currency_id,
    )
    premium = fields.Monetary(
        string="Net premium",
        groups=AMOUNTS_GROUP,
        currency_field="currency_id",
        tracking=True,
        help="Technical cost of the insurance, without taxes or surcharges.",
    )
    premium_total = fields.Monetary(
        string="Total premium",
        groups=AMOUNTS_GROUP,
        currency_field="currency_id",
        tracking=True,
        help="Amount the company actually pays: net premium plus taxes and "
        "surcharges.",
    )
    sum_insured_total = fields.Monetary(
        string="Total sum insured",
        groups=AMOUNTS_GROUP,
        currency_field="currency_id",
        compute="_compute_sum_insured_total",
        store=True,
        help="Sum of the sums insured of the active insured objects.",
    )
    deductible_type = fields.Selection(
        selection=[("amount", "Amount"), ("percentage", "Percentage")],
        string="Deductible type",
        tracking=True,
    )
    deductible_amount = fields.Monetary(
        string="Deductible amount",
        groups=AMOUNTS_GROUP,
        currency_field="currency_id",
        tracking=True,
    )
    deductible_percent = fields.Float(
        string="Deductible (%)",
        groups=AMOUNTS_GROUP,
        digits=(5, 2),
        tracking=True,
    )
    coverage = fields.Html(string="Coverages", help="Coverages and clauses of the policy.")
    tag_ids = fields.Many2many(
        comodel_name="insurance.policy.tag",
        relation="insurance_policy_tag_rel",
        column1="policy_id",
        column2="tag_id",
        string="Tags",
    )
    note = fields.Html(string="Notes")
    object_ids = fields.One2many(
        comodel_name="insurance.policy.object",
        inverse_name="policy_id",
        string="Insured objects",
    )
    object_count = fields.Integer(
        string="Active objects",
        compute="_compute_sum_insured_total",
        store=True,
    )
    covered_today = fields.Boolean(
        string="Covered today",
        compute="_compute_covered_today",
        search="_search_covered_today",
        help="Confirmed, not cancelled, and today is within its validity "
        "dates (both included).",
    )
    is_locked = fields.Boolean(string="Locked", compute="_compute_is_locked")

    # Renewal ------------------------------------------------------------------
    previous_policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Previous policy",
        readonly=True,
        copy=False,
        index=True,
        ondelete="set null",
        help="Policy this one renews.",
    )
    renewed_by_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Renewed by",
        readonly=True,
        copy=False,
        index=True,
        ondelete="set null",
        help="Policy created when this one was renewed.",
    )
    renewal_count = fields.Integer(
        string="Renewal history",
        compute="_compute_renewal_count",
    )
    keep_number_on_renewal = fields.Boolean(
        string="Keep number on renewal",
        tracking=True,
        help="The insurer keeps the same policy number on renewals: the "
        "renewal draft is created with this number already filled in.",
    )
    non_renewal_reason = fields.Text(string="Non-renewal reason", tracking=True, copy=False)
    non_renewal_date = fields.Date(string="Marked not to renew on", readonly=True, copy=False)
    non_renewal_sent_date = fields.Datetime(
        string="Non-renewal instruction sent on",
        readonly=True,
        copy=False,
    )
    renewal_request_sent_date = fields.Datetime(
        string="Renewal request sent on",
        readonly=True,
        copy=False,
    )

    # Documents ----------------------------------------------------------------
    attachment_ids = fields.One2many(
        comodel_name="ir.attachment",
        inverse_name="res_id",
        domain=[("res_model", "=", "insurance.policy")],
        string="Documents",
    )
    document_count = fields.Integer(
        string="Documents count",
        compute="_compute_document_count",
        help="Files attached to the policy, from the Documents tab or the chatter.",
    )

    # Endorsements -------------------------------------------------------------
    endorsement_ids = fields.One2many(
        comodel_name="insurance.endorsement",
        inverse_name="policy_id",
        string="Endorsements",
    )
    endorsement_count = fields.Integer(string="Endorsement count", compute="_compute_endorsement_count")
    endorsement_premium_total = fields.Monetary(
        string="Endorsements premium",
        currency_field="currency_id",
        compute="_compute_endorsement_premium",
        store=True,
        groups=AMOUNTS_GROUP,
        help="Sum of the premium differences of the confirmed endorsements.",
    )
    premium_with_endorsements = fields.Monetary(
        string="Total premium with endorsements",
        currency_field="currency_id",
        compute="_compute_endorsement_premium",
        store=True,
        groups=AMOUNTS_GROUP,
    )

    # Accounting parameters (section 4.9) ----------------------------------------
    billing_mode = fields.Selection(
        selection=BILLING_MODES,
        string="Billing mode",
        compute="_compute_accounting_defaults",
        store=True,
        readonly=False,
        precompute=True,
        tracking=True,
        help="One bill per policy (with one due date per installment) or one "
        "bill per installment. Taken from the branch or the settings when the "
        "policy is created.",
    )
    accrual_method = fields.Selection(
        selection=ACCRUAL_METHODS,
        string="Accrual method",
        compute="_compute_accounting_defaults",
        store=True,
        readonly=False,
        precompute=True,
        tracking=True,
        help="How the premium is spread as an expense over the policy months. "
        "Taken from the settings when the policy is created.",
    )
    payment_mode_id = fields.Many2one(
        comodel_name="insurance.payment.mode",
        string="Payment mode",
        compute="_compute_accounting_defaults",
        store=True,
        readonly=False,
        precompute=True,
        tracking=True,
        check_company=True,
        help="How the installments are paid by default; each installment can "
        "use another one.",
    )
    expense_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Expense account",
        check_company=True,
        tracking=True,
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Leave empty to use the branch account or, if empty too, the one "
        "of the insurance product of the settings.",
    )
    prepaid_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Prepaid insurance account",
        check_company=True,
        tracking=True,
        groups="account.group_account_invoice,account.group_account_readonly",
        help="Asset account of the premium still to accrue (module accrual). "
        "Leave empty to use the one of the settings.",
    )

    # Installments, bills, accrual (Fase 2) ------------------------------------
    installment_ids = fields.One2many(
        comodel_name="insurance.installment",
        inverse_name="policy_id",
        string="Installments",
    )
    installment_count = fields.Integer(string="Installment count", compute="_compute_installment_totals")
    installments_total = fields.Monetary(
        string="Installments total",
        currency_field="currency_id",
        compute="_compute_installment_totals",
        groups=AMOUNTS_GROUP,
    )
    installment_difference = fields.Monetary(
        string="Difference with the installments",
        currency_field="currency_id",
        compute="_compute_installment_totals",
        groups=AMOUNTS_GROUP,
        help="Total premium with endorsements minus the installments: it must be zero.",
    )
    has_debt = fields.Boolean(
        string="With debt",
        compute="_compute_has_debt",
        store=True,
        index=True,
        help="Some installment is overdue and unpaid: the insurer may suspend the coverage.",
    )
    invoice_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="insurance_policy_id",
        string="Bills",
        domain=[("move_type", "in", ("in_invoice", "in_refund"))],
    )
    invoice_count = fields.Integer(string="Bill count", compute="_compute_invoice_amounts")
    amount_invoiced = fields.Monetary(
        string="Billed",
        currency_field="currency_id",
        compute="_compute_invoice_amounts",
        groups=AMOUNTS_GROUP,
    )
    amount_paid = fields.Monetary(
        string="Amount paid",
        currency_field="currency_id",
        compute="_compute_invoice_amounts",
        groups=AMOUNTS_GROUP,
    )
    amount_due = fields.Monetary(
        string="Balance due",
        currency_field="currency_id",
        compute="_compute_invoice_amounts",
        groups=AMOUNTS_GROUP,
    )
    accrual_line_ids = fields.One2many(
        comodel_name="insurance.accrual.line",
        inverse_name="policy_id",
        string="Accrual plan",
    )
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
    in_progress = fields.Boolean(
        string="Running policy",
        copy=False,
        tracking=True,
        help="Policy already running at the go-live (initial load): its "
        "installments before the one it continues from are historical, and "
        "only the amount still to accrue is accrued.",
    )
    continue_from_installment = fields.Integer(
        string="Continues from installment",
        copy=False,
        default=1,
        tracking=True,
        help="Running policy: first installment managed in Odoo (e.g. 4 of 12).",
    )
    unaccrued_amount = fields.Monetary(
        string="Amount still to accrue at go-live",
        copy=False,
        currency_field="company_currency_id",
        tracking=True,
        groups=AMOUNTS_GROUP,
        help="Running policy: premium not accrued yet at the go-live date, in "
        "company currency. It must match its share of the opening balance of "
        "the prepaid insurance account.",
    )

    # Alerts -------------------------------------------------------------------
    alert_days = fields.Char(
        string="Alert days",
        tracking=True,
        help="Days before the end date on which an expiry notice is sent, as "
        "a comma-separated list (e.g. 30,15,7). Leave empty to use the value "
        "of the branch or, if empty too, of the insurance settings.",
    )
    effective_alert_days = fields.Char(
        string="Alert days applied",
        compute="_compute_effective_alert_days",
        help="Thresholds actually used for this policy: the policy value, else "
        "the branch value, else the insurance settings value.",
    )
    notify_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_policy_notify_user_rel",
        column1="policy_id",
        column2="user_id",
        string="Users to notify",
        domain=[("share", "=", False)],
        help="Added to the users of the insurance settings, of the branch and "
        "to the responsible.",
    )
    non_renewal_send_mode = fields.Selection(
        selection=[("manual", "Manual"), ("automatic", "Automatic")],
        string="Non-renewal instruction sending",
        required=True,
        default=lambda self: self.env.company.insurance_non_renewal_send_mode or "manual",
        help="Manual: sent from the Do not renew button. Automatic: sent by "
        "the daily process the configured days before the end date, if the "
        "renewal type is Do not renew.",
    )
    non_renewal_days = fields.Integer(
        string="Send non-renewal instruction (days before)",
        default=lambda self: self.env.company.insurance_non_renewal_days,
    )
    alert_ids = fields.One2many(
        comodel_name="insurance.policy.alert",
        inverse_name="policy_id",
        string="Alerts sent",
    )
    days_left = fields.Integer(
        string="Days left",
        compute="_compute_days_left",
        help="Days from today to the end date (0 = it expires today).",
    )
    expires_today = fields.Boolean(
        string="Expires today",
        compute="_compute_days_left",
        search="_search_expires_today",
    )

    # Allows reusing the insurer's number on a renewal (other start date);
    # drafts without a number never collide (NULL values are distinct).
    _number_uniq = models.UniqueIndex(
        "(company_id, insurer_id, policy_number, date_from) WHERE policy_number IS NOT NULL",
        "There is already a policy with this number for this insurer, company "
        "and start date.",
    )

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends("name", "policy_number")
    def _compute_display_name(self):
        for policy in self:
            if policy.policy_number:
                policy.display_name = f"{policy.name} - {policy.policy_number}"
            else:
                policy.display_name = policy.name

    @api.depends("date_from", "date_to")
    def _compute_duration(self):
        for policy in self:
            if policy.date_from and policy.date_to and policy.date_to > policy.date_from:
                months, days = self._get_duration_parts(policy.date_from, policy.date_to)
                policy.duration_months = months
                policy.duration_days = days
            else:
                policy.duration_months = 0
                policy.duration_days = 0

    @api.depends("date_from", "date_to", "company_id")
    def _compute_duration_warning(self):
        for policy in self:
            policy.duration_warning = policy._get_duration_issue() or False

    @api.depends("object_ids.sum_insured", "object_ids.state")
    def _compute_sum_insured_total(self):
        for policy in self:
            active_objects = policy.object_ids.filtered(lambda obj: obj.state == "active")
            policy.sum_insured_total = sum(active_objects.mapped("sum_insured"))
            policy.object_count = len(active_objects)

    @api.depends("state", "date_from", "date_to")
    @api.depends_context("insurance_today")
    def _compute_covered_today(self):
        today = self._get_today()
        for policy in self:
            policy.covered_today = bool(
                policy.state not in UNCOVERED_STATES
                and policy.date_from
                and policy.date_to
                and policy.date_from <= today <= policy.date_to
            )

    def _search_covered_today(self, operator, value):
        if operator != "in":
            return NotImplemented
        today = self._get_today()
        covered = Domain(
            [
                ("state", "not in", UNCOVERED_STATES),
                ("date_from", "<=", today),
                ("date_to", ">=", today),
            ]
        )
        if True in value and False in value:
            return Domain.TRUE
        if True in value:
            return covered
        return ~covered

    @api.depends("state")
    def _compute_is_locked(self):
        for policy in self:
            policy.is_locked = policy.state in LOCKED_STATES

    @api.depends("installment_ids.amount", "installment_ids.cancelled", "premium_with_endorsements")
    def _compute_installment_totals(self):
        for policy in self:
            active = policy.installment_ids.filtered(lambda i: not i.cancelled)
            policy.installment_count = len(active)
            total = sum(active.sudo().mapped("amount"))
            policy.installments_total = total
            policy.installment_difference = policy.sudo().premium_with_endorsements - total if active else 0.0

    @api.depends("installment_ids.state")
    def _compute_has_debt(self):
        for policy in self:
            policy.has_debt = any(state == "overdue" for state in policy.installment_ids.mapped("state"))

    def _compute_invoice_amounts(self):
        # Insurance users without accounting rights still see the totals.
        for policy in self:
            moves = policy.sudo().invoice_ids.filtered(lambda m: m.state == "posted")
            invoiced = paid = due = 0.0
            for move in moves:
                sign = -1 if move.move_type == "in_refund" else 1
                invoiced += sign * move.amount_total
                due += sign * move.amount_residual
            paid = invoiced - due
            policy.invoice_count = len(policy.sudo().invoice_ids)
            policy.amount_invoiced = invoiced
            policy.amount_paid = paid
            policy.amount_due = due

    def _compute_endorsement_count(self):
        counts = dict(
            self.env["insurance.endorsement"]._read_group(
                [("policy_id", "in", self.ids)], groupby=["policy_id"], aggregates=["__count"]
            )
        )
        for policy in self:
            policy.endorsement_count = counts.get(policy, 0)

    @api.depends("premium_total", "endorsement_ids.state", "endorsement_ids.premium_difference")
    def _compute_endorsement_premium(self):
        for policy in self:
            confirmed = policy.endorsement_ids.filtered(lambda e: e.state == "confirmed")
            policy.endorsement_premium_total = sum(confirmed.sudo().mapped("premium_difference"))
            policy.premium_with_endorsements = policy.premium_total + policy.endorsement_premium_total

    @api.depends("branch_id", "company_id")
    def _compute_accounting_defaults(self):
        for policy in self:
            company = policy.company_id or self.env.company
            policy.billing_mode = policy.branch_id.billing_mode or company.insurance_billing_mode or "policy"
            policy.accrual_method = company.insurance_accrual_method or "module"
            if not policy.payment_mode_id or policy.payment_mode_id.company_id != company:
                policy.payment_mode_id = company.insurance_default_payment_mode_id

    @api.depends("alert_days", "branch_id.alert_days", "company_id.insurance_alert_days")
    def _compute_effective_alert_days(self):
        for policy in self:
            policy.effective_alert_days = ",".join(str(days) for days in policy._get_alert_days())

    @api.depends("state", "date_to")
    @api.depends_context("insurance_today")
    def _compute_days_left(self):
        today = self._get_today()
        for policy in self:
            policy.days_left = (policy.date_to - today).days if policy.date_to else 0
            policy.expires_today = policy.state in ACTIVE_STATES and policy.date_to == today

    def _search_expires_today(self, operator, value):
        if operator != "in":
            return NotImplemented
        domain = Domain([("state", "in", ACTIVE_STATES), ("date_to", "=", self._get_today())])
        if True in value and False in value:
            return Domain.TRUE
        return domain if True in value else ~domain

    def _compute_document_count(self):
        counts = dict(
            self.env["ir.attachment"]._read_group(
                [("res_model", "=", self._name), ("res_id", "in", self.ids)],
                groupby=["res_id"],
                aggregates=["__count"],
            )
        )
        for policy in self:
            policy.document_count = counts.get(policy.id, 0)

    @api.depends("previous_policy_id", "renewed_by_id")
    def _compute_renewal_count(self):
        for policy in self:
            policy.renewal_count = len(policy._get_renewal_chain()) if policy.id else 0

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @api.model
    def _get_today(self):
        """Today's date, overridable through the ``insurance_today`` context
        key (used by the scheduled processes and the tests)."""
        return self.env.context.get("insurance_today") or fields.Date.context_today(self)

    @api.model
    def _get_duration_parts(self, date_from, date_to):
        """Return (months, days) of a validity period, ``date_to`` included.

        1 Jan - 31 Dec is (12, 0); 15 Mar - 14 Sep is (6, 0).
        """
        delta = relativedelta(date_to + relativedelta(days=1), date_from)
        return delta.years * 12 + delta.months, delta.days

    def _get_duration_issue(self):
        """Return a message when the duration is outside the company limits,
        or ``False`` when it is fine (or the dates are incomplete)."""
        self.ensure_one()
        if not (self.date_from and self.date_to) or self.date_to <= self.date_from:
            return False
        company = self.company_id or self.env.company
        min_months = company.insurance_min_duration_months
        max_months = company.insurance_max_duration_months
        end_exclusive = self.date_to + relativedelta(days=1)
        if end_exclusive < self.date_from + relativedelta(months=min_months):
            return self.env._(
                "The policy lasts less than the minimum of %(months)s month(s).",
                months=min_months,
            )
        if end_exclusive > self.date_from + relativedelta(months=max_months):
            return self.env._(
                "The policy lasts more than the maximum of %(months)s month(s).",
                months=max_months,
            )
        return False

    @api.model
    def _get_policy_sequence(self, company):
        """Return the policy reference sequence of ``company``, creating it on
        first use so each company numbers its policies independently."""
        sequence = (
            self.env["ir.sequence"]
            .sudo()
            .search([("code", "=", "insurance.policy"), ("company_id", "=", company.id)], limit=1)
        )
        if not sequence:
            sequence = (
                self.env["ir.sequence"]
                .sudo()
                .create(
                    {
                        "name": f"Insurance policy ({company.name})",
                        "code": "insurance.policy",
                        "prefix": "SEG/%(range_year)s/",
                        "padding": 4,
                        "use_date_range": True,
                        "company_id": company.id,
                    }
                )
            )
        return sequence

    def _get_locked_writable_fields(self):
        """Fields that may still be written on a locked policy: its documents
        (requirements section 5: read-only "except attachments")."""
        return {"attachment_ids"}

    def _get_alert_days(self):
        """Alert thresholds of this policy, largest first. The most specific
        level with a value wins: policy, then branch, then settings."""
        self.ensure_one()
        for value in (self.alert_days, self.branch_id.alert_days, self.company_id.insurance_alert_days):
            thresholds = parse_alert_days(self.env, value)
            if thresholds:
                return thresholds
        return []

    def _get_notify_users(self):
        """Users notified about this policy: union of the settings, branch and
        policy users plus the responsible (active internal users only)."""
        self.ensure_one()
        users = (
            self.company_id.insurance_notify_user_ids
            | self.branch_id.notify_user_ids
            | self.notify_user_ids
            | self.user_id
        )
        return users.filtered(lambda user: user.active and not user.share)

    def _get_insurance_product(self):
        """Service product of the insurance bills: the branch one, else the
        one of the settings (section 4.9)."""
        self.ensure_one()
        return self.branch_id.product_id or self.company_id.insurance_product_id

    def _get_expense_account(self):
        """Expense account: policy > branch > insurance product."""
        self.ensure_one()
        policy = self.sudo()
        product = policy._get_insurance_product()
        accounts = product.product_tmpl_id.with_company(policy.company_id).get_product_accounts() if product else {}
        return policy.expense_account_id or policy.branch_id.expense_account_id or accounts.get("expense") or self.env["account.account"]

    def _get_prepaid_account(self):
        """Prepaid insurance account (module accrual): policy > settings."""
        self.ensure_one()
        policy = self.sudo()
        return policy.prepaid_account_id or policy.company_id.insurance_prepaid_account_id

    def _get_analytic_distribution(self):
        """Analytic distribution: policy > branch."""
        self.ensure_one()
        return self.analytic_distribution or self.branch_id.analytic_distribution or {}

    def _get_renewal_chain(self):
        """Return every policy of this policy's renewal history (previous
        ones and renewals), this one included."""
        self.ensure_one()
        chain = self
        previous = self.previous_policy_id
        while previous and previous not in chain:
            chain |= previous
            previous = previous.previous_policy_id
        following = self.renewed_by_id
        while following and following not in chain:
            chain |= following
            following = following.renewed_by_id
        return chain

    def _get_mail_objects(self):
        """Active insured objects, as shown in the emails."""
        self.ensure_one()
        return self.object_ids.filtered(lambda obj: obj.state == "active")

    def _get_mail_object_label(self, insured_object):
        """One-line label of an insured object for the emails."""
        if insured_object.license_plate and insured_object.license_plate not in insured_object.name:
            return f"{insured_object.name} ({insured_object.license_plate})"
        return insured_object.name

    def _get_mail_validity(self):
        """Validity as text for the emails, in the rendering language, with
        the coverage time of the company (e.g. "01/03/2026 - 28/02/2027,
        12:00")."""
        self.ensure_one()
        if not (self.date_from and self.date_to):
            return ""
        env = self.env
        coverage_time = self.company_id.insurance_coverage_time or "12"
        if coverage_time == "0":
            end = env._(
                "until 0:00 on %(date)s",
                date=format_date(env, self.date_to + relativedelta(days=1)),
            )
        else:
            end = env._("until 12:00 on %(date)s", date=format_date(env, self.date_to))
        return env._(
            "from %(start)s %(end)s",
            start=format_date(env, self.date_from),
            end=end,
        )

    # -------------------------------------------------------------------------
    # Constraints and onchanges
    # -------------------------------------------------------------------------

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for policy in self:
            if policy.date_from and policy.date_to and policy.date_to <= policy.date_from:
                raise ValidationError(
                    self.env._(
                        "Policy %(policy)s: the end date must be after the start date.",
                        policy=policy.display_name,
                    )
                )

    @api.constrains("date_from", "date_to", "state", "company_id")
    def _check_duration_block(self):
        for policy in self:
            if (
                policy.state == "draft"
                or policy.company_id.insurance_duration_check != "block"
                or self.env.context.get("insurance_skip_duration_check")
            ):
                continue
            issue = policy._get_duration_issue()
            if issue:
                raise ValidationError(
                    self.env._("Policy %(policy)s: %(issue)s", policy=policy.display_name, issue=issue)
                )

    @api.constrains("alert_days")
    def _check_alert_days(self):
        for policy in self:
            parse_alert_days(self.env, policy.alert_days)

    @api.constrains("non_renewal_days")
    def _check_non_renewal_days(self):
        for policy in self:
            if policy.non_renewal_days < 0:
                raise ValidationError(
                    self.env._("The days before sending the non-renewal instruction cannot be negative.")
                )

    def _get_suggested_unaccrued_amount(self, continue_from):
        """Amount still to accrue at go-live suggested for a running policy
        continuing from ``continue_from``: the net premium share (as billed)
        of the installments managed in Odoo, in company currency. Without
        installments yet, the premium share of the remaining ones (a monthly
        installment per month of validity)."""
        self.ensure_one()
        policy = self.sudo()
        installments = policy.installment_ids.filtered(lambda i: not i.endorsement_id and not i.cancelled)
        if installments:
            amount = sum(
                installments.filtered(
                    lambda i: not policy._is_historical_installment(i.number, i.due_date, None, continue_from)
                ).mapped("amount")
            )
            if policy.premium and policy.premium_total:
                amount = amount * policy.premium / policy.premium_total
        else:
            if not (policy.date_from and policy.date_to):
                return 0.0
            months, days = policy._get_duration_parts(policy.date_from, policy.date_to)
            count = max(months + (1 if days else 0), 1)
            amount = policy.premium * max(count - (continue_from or 1) + 1, 0) / count
        currency = policy.currency_id or policy.company_id.currency_id
        company = policy.company_id or self.env.company
        date = company.insurance_go_live_date or fields.Date.context_today(self)
        return currency._convert(amount, company.currency_id, company, date)

    @api.onchange("in_progress", "continue_from_installment")
    def _onchange_suggest_unaccrued_amount(self):
        """Suggest the amount still to accrue; a value typed by the user (not
        one of the suggestions) is never replaced."""
        if not self.in_progress or not self.env.user.has_group(AMOUNTS_GROUP):
            return
        currency = self.company_id.currency_id or self.env.company.currency_id
        current = self.sudo().unaccrued_amount
        if not currency.is_zero(current):
            count = max(len(self.installment_ids), 12)
            suggestions = [self._get_suggested_unaccrued_amount(number) for number in range(1, count + 1)]
            if not any(currency.compare_amounts(current, suggestion) == 0 for suggestion in suggestions):
                return
        self.unaccrued_amount = currency.round(self._get_suggested_unaccrued_amount(self.continue_from_installment))

    @api.onchange("date_from", "date_to")
    def _onchange_dates_duration(self):
        issue = self._get_duration_issue()
        if issue:
            return {"warning": {"title": self.env._("Policy duration"), "message": issue}}
        return None

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        default_name = self.env._("New")
        for vals in vals_list:
            if "alert_days" in vals:
                vals["alert_days"] = format_alert_days(self.env, vals["alert_days"])
            if "state" in vals and vals["state"] != "draft" and not self.env.context.get(LIFECYCLE_CTX):
                raise UserError(self.env._("A policy is always created as a draft."))
            if not vals.get("name") or vals["name"] == default_name:
                company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
                vals["name"] = self._get_policy_sequence(company).next_by_id(
                    sequence_date=vals.get("date_from")
                )
        return super().create(vals_list)

    def write(self, vals):
        if "alert_days" in vals:
            vals["alert_days"] = format_alert_days(self.env, vals["alert_days"])
        if not self.env.context.get(LIFECYCLE_CTX):
            if "state" in vals:
                raise UserError(
                    self.env._("The policy status can only be changed with its action buttons.")
                )
            confirmed = self.filtered(lambda p: p.state in CONFIRMED_STATES)
            contract = CONTRACT_FIELDS.intersection(vals)
            if confirmed and contract and not self.env.context.get(ENDORSEMENT_CTX):
                raise UserError(
                    self.env._(
                        "Policy %(policy)s is confirmed: %(fields)s can only be changed with an "
                        "endorsement (or, by an administrator, after resetting it to draft).",
                        policy=confirmed[0].display_name,
                        fields=", ".join(self._fields[fname].get_description(self.env)["string"] for fname in sorted(contract)),
                    )
                )
            locked = self.filtered("is_locked")
            if locked:
                allowed = self._get_locked_writable_fields()
                blocked = [
                    fname
                    for fname in vals
                    if fname not in allowed and not fname.startswith(("message_", "activity_"))
                ]
                if blocked:
                    raise UserError(
                        self.env._(
                            "Policy %(policy)s is %(state)s and can no longer be modified.",
                            policy=locked[0].display_name,
                            state=dict(self._fields["state"]._description_selection(self.env))[
                                locked[0].state
                            ],
                        )
                    )
        res = super().write(vals)
        if "date_to" in vals or "date_from" in vals:
            self.filtered(lambda p: p.state not in UNCOVERED_STATES)._apply_lifecycle_state()
        if {"in_progress", "continue_from_installment"}.intersection(vals):
            self._sync_historical_installments()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        if any(policy.state != "draft" for policy in self):
            raise UserError(self.env._("Only draft policies can be deleted."))

    def unlink(self):
        previous = self.previous_policy_id - self
        res = super().unlink()
        # Deleting a renewal draft clears the link (ondelete set null): the
        # renewed policy goes back to the state its own decision dictates.
        previous = previous.exists()
        if previous:
            previous.invalidate_recordset(["renewed_by_id"])
            for policy in previous:
                policy._message_log(body=self.env._("The renewal draft of this policy was deleted."))
            previous._apply_lifecycle_state()
        return res

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        kind = self.env.context.get(MAIL_KIND_CTX)
        if kind in MAIL_KIND_FIELDS and kwargs.get("message_type") == "comment":
            self.with_context(**{LIFECYCLE_CTX: True}).write(
                {MAIL_KIND_FIELDS[kind]: fields.Datetime.now()}
            )
        return message

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def _get_lifecycle_state(self, today):
        """Return the state this confirmed policy should be in on ``today``.

        Not started while its start date is still ahead. In force until its
        end date (inclusive), Expiring from its first alert threshold. From the
        day after the end date, it ends as Renewed (a renewal exists), Not
        renewed (marked "do not renew") or Expired.
        """
        self.ensure_one()
        if self.state in UNCOVERED_STATES:
            return self.state
        if self.date_from > today:
            return "not_started"
        if self.date_to < today:
            if self.renewed_by_id:
                return "renewed"
            if self.renewal_type == "no_renew":
                return "not_renewed"
            return "expired"
        # Until its end date (included) it is in force, and Expiring once the
        # first alert threshold is reached (always on its end date).
        days_left = (self.date_to - today).days
        if days_left <= max(self._get_alert_days() or [0]):
            return "expiring"
        return "in_force"

    def _apply_lifecycle_state(self, today=None):
        """Move each policy to the state it should be in on ``today``.

        :return: the policies whose state changed.
        """
        today = today or self._get_today()
        changed = self.browse()
        for policy in self:
            new_state = policy._get_lifecycle_state(today)
            if new_state != policy.state:
                policy.with_context(**{LIFECYCLE_CTX: True}).write({"state": new_state})
                changed |= policy
        return changed

    def _check_can_confirm(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                self.env._("Policy %(policy)s is not a draft.", policy=self.display_name)
            )
        missing = []
        if not self.policy_number:
            missing.append(self.env._("policy number"))
        if not self.date_from:
            missing.append(self.env._("valid from"))
        if not self.date_to:
            missing.append(self.env._("valid to"))
        if missing:
            raise UserError(
                self.env._(
                    "To confirm policy %(policy)s, fill in: %(fields)s.",
                    policy=self.display_name,
                    fields=", ".join(missing),
                )
            )
        issue = self._get_duration_issue()
        if issue and self.company_id.insurance_duration_check == "block":
            raise ValidationError(
                self.env._("Policy %(policy)s: %(issue)s", policy=self.display_name, issue=issue)
            )

    def _get_zero_amount_policies(self):
        """Policies whose premium and/or total premium is zero."""
        return self.filtered(lambda policy: not policy.sudo().premium or not policy.sudo().premium_total)

    def action_confirm(self):
        today = self._get_today()
        for policy in self:
            policy._check_can_confirm()
        zero_amounts = self._get_zero_amount_policies()
        if (
            zero_amounts
            and self.env.context.get(AMOUNT_CHECK_CTX)
            and self.env.user.has_group(AMOUNTS_GROUP)
        ):
            # Once confirmed, premiums only change through an endorsement:
            # warn before, the user may still confirm.
            return {
                "type": "ir.actions.act_window",
                "name": self.env._("Premium at zero"),
                "res_model": "insurance.policy.confirm.warning",
                "view_mode": "form",
                "target": "new",
                "context": {"default_policy_ids": self.ids},
            }
        for policy in self:
            issue = policy._get_duration_issue()
            policy.with_context(**{LIFECYCLE_CTX: True}).write({"state": "in_force"})
            if issue:
                policy._message_log(
                    body=self.env._("Confirmed with a duration warning: %(issue)s", issue=issue)
                )
            if policy in zero_amounts:
                policy._message_log(body=self.env._("Confirmed with the premium and/or total premium at zero."))
        self._apply_lifecycle_state(today)
        return True

    def _check_can_reset_to_draft(self):
        """Only without posted bills nor payments (section 5)."""
        self.ensure_one()
        policy = self.sudo()
        if policy.invoice_ids.filtered(lambda m: m.state == "posted") or policy.installment_ids.payment_id.filtered(
            lambda p: p.state not in ("draft", "canceled")
        ):
            raise UserError(
                self.env._(
                    "Policy %(policy)s has posted bills or payments: it cannot be reset to draft.",
                    policy=self.display_name,
                )
            )
        if self.state in ("draft", "cancelled"):
            raise UserError(
                self.env._(
                    "Policy %(policy)s cannot be reset to draft from its current status.",
                    policy=self.display_name,
                )
            )

    def action_reset_to_draft(self):
        if not self.env.user.has_group("insurance_management.group_insurance_manager"):
            raise AccessError(
                self.env._("Only an insurance administrator can reset a policy to draft.")
            )
        for policy in self:
            policy._check_can_reset_to_draft()
        self.with_context(**{LIFECYCLE_CTX: True}).write({"state": "draft"})
        return True

    # -------------------------------------------------------------------------
    # Renewal and non-renewal
    # -------------------------------------------------------------------------

    def _check_can_renew(self):
        self.ensure_one()
        if self.renewed_by_id:
            raise UserError(
                self.env._(
                    "Policy %(policy)s is already renewed by %(renewal)s.",
                    policy=self.display_name,
                    renewal=self.renewed_by_id.display_name,
                )
            )
        if self.state not in ("expiring", "expired"):
            raise UserError(
                self.env._(
                    "Policy %(policy)s can only be renewed when it is expiring or expired.",
                    policy=self.display_name,
                )
            )

    def _prepare_renewal_vals(self):
        """Values of the renewal draft: same parties, coverages and active
        objects, validity starting the day after the end date and lasting
        the same. Read as superuser: amounts are copied even when the user
        cannot see them (see action_renew)."""
        self.ensure_one()
        self = self.sudo()
        months, days = self._get_duration_parts(self.date_from, self.date_to)
        date_from = self.date_to + relativedelta(days=1)
        date_to = date_from + relativedelta(months=months, days=days) - relativedelta(days=1)
        return {
            "policy_number": self.policy_number if self.keep_number_on_renewal else False,
            "keep_number_on_renewal": self.keep_number_on_renewal,
            "branch_id": self.branch_id.id,
            "insurer_id": self.insurer_id.id,
            "producer_id": self.producer_id.id,
            "user_id": self.user_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "date_from": date_from,
            "date_to": date_to,
            "coverage": self.coverage,
            "deductible_type": self.deductible_type,
            "deductible_amount": self.deductible_amount,
            "deductible_percent": self.deductible_percent,
            "tag_ids": [fields.Command.set(self.tag_ids.ids)],
            "previous_policy_id": self.id,
            "alert_days": self.alert_days,
            "notify_user_ids": [fields.Command.set(self.notify_user_ids.ids)],
            "non_renewal_send_mode": self.non_renewal_send_mode,
            "non_renewal_days": self.non_renewal_days,
            "billing_mode": self.billing_mode,
            "accrual_method": self.accrual_method,
            "payment_mode_id": self.payment_mode_id.id,
            "expense_account_id": self.expense_account_id.id,
            "prepaid_account_id": self.prepaid_account_id.id,
            "analytic_distribution": self.analytic_distribution,
            "object_ids": [
                fields.Command.create(
                    {
                        "sequence": obj.sequence,
                        "name": obj.name,
                        "insured_item_id": obj.insured_item_id.id,
                        "license_plate": obj.license_plate,
                        "chassis_number": obj.chassis_number,
                        "engine_number": obj.engine_number,
                        "sum_insured": obj.sum_insured,
                        "coverage": obj.coverage,
                    }
                )
                for obj in self._get_mail_objects()
            ],
        }

    def action_renew(self):
        """Create the renewal draft and link both policies. The state of this
        policy only changes when it reaches its end date (or right away for
        a late renewal of an expired policy)."""
        self.ensure_one()
        self._check_can_renew()
        self.check_access("create")
        # Created as superuser so the amounts (deductible, sums insured) are
        # copied even for users who cannot see them; access was checked above.
        renewal = self.sudo().create(self._prepare_renewal_vals()).sudo(False)
        previous_type = self.renewal_type
        self.with_context(**{LIFECYCLE_CTX: True}).write(
            {"renewed_by_id": renewal.id, "renewal_type": "renew"}
        )
        if previous_type == "no_renew":
            note = self.env._("Renewed although it had been marked not to renew.")
            if self.non_renewal_sent_date:
                note = self.env._(
                    "Renewed although it had been marked not to renew; the non-renewal "
                    "instruction was already sent to the producer on %(date)s.",
                    date=fields.Datetime.to_string(self.non_renewal_sent_date),
                )
            self._message_log(body=note)
        renewal._message_log(
            body=self.env._("Renewal of policy %(policy)s.", policy=self.display_name)
        )
        self._apply_lifecycle_state()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": renewal.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_document_upload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Upload document"),
            "res_model": "insurance.policy.document.upload",
            "view_mode": "form",
            "target": "new",
            "context": {"default_policy_id": self.id},
        }

    def action_view_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "insurance_management.insurance_policy_document_action"
        )
        action["domain"] = [("res_model", "=", self._name), ("res_id", "=", self.id)]
        action["context"] = {"default_res_model": self._name, "default_res_id": self.id}
        return action

    def action_new_endorsement(self):
        self.ensure_one()
        if self.state not in CONFIRMED_STATES:
            raise UserError(
                self.env._("Endorsements can only be added to policies not started yet, in force or expiring.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("New endorsement"),
            "res_model": "insurance.endorsement",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_policy_id": self.id,
                "default_effective_date": fields.Date.to_string(max(self._get_today(), self.date_from)),
            },
        }

    def action_view_endorsements(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_endorsement_action")
        action["domain"] = [("policy_id", "=", self.id)]
        action["context"] = {"default_policy_id": self.id}
        return action

    def action_view_renewals(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "insurance_management.insurance_policy_action"
        )
        action["domain"] = [("id", "in", self._get_renewal_chain().ids)]
        action["context"] = {}
        return action

    def _check_can_mark_non_renewal(self):
        self.ensure_one()
        if self.state not in ("in_force", "expiring") or self.renewed_by_id:
            raise UserError(
                self.env._(
                    "Policy %(policy)s can only be marked not to renew while it is in "
                    "force and not renewed yet.",
                    policy=self.display_name,
                )
            )

    def action_open_non_renewal_wizard(self):
        self.ensure_one()
        self._check_can_mark_non_renewal()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Do not renew"),
            "res_model": "insurance.policy.non.renewal",
            "view_mode": "form",
            "target": "new",
            "context": {"default_policy_id": self.id},
        }

    def _mark_non_renewal(self, reason):
        for policy in self:
            policy._check_can_mark_non_renewal()
        self.write(
            {
                "renewal_type": "no_renew",
                "non_renewal_reason": reason,
                "non_renewal_date": self._get_today(),
            }
        )

    def _send_producer_template(self, template_xmlid, kind, cc_insurer=False, cc_responsible=False):
        """Email a template to the producer of each policy, kept in the chatter
        as a sent message, optionally copying the insurer and the responsible."""
        template = self.env.ref(template_xmlid)
        for policy in self:
            if not policy.producer_id.email:
                raise UserError(
                    self.env._(
                        "The producer %(producer)s has no email address.",
                        producer=policy.producer_id.display_name,
                    )
                )
            copies = self.env["res.partner"]
            if cc_insurer and policy.insurer_id.email:
                copies |= policy.insurer_id
            if cc_responsible:
                copies |= policy.user_id.partner_id
            policy.with_context(**{MAIL_KIND_CTX: kind}).message_post_with_source(
                template,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=(policy.producer_id | copies).ids,
            )

    def _send_non_renewal_instruction(self, cc_insurer=False, cc_responsible=False):
        self._send_producer_template(
            "insurance_management.mail_template_policy_non_renewal",
            "non_renewal",
            cc_insurer=cc_insurer,
            cc_responsible=cc_responsible,
        )

    def action_request_renewal(self):
        """Open the email composer with the renewal request for the producer."""
        self.ensure_one()
        if self.state not in ("in_force", "expiring") or self.renewed_by_id:
            raise UserError(
                self.env._(
                    "A renewal can only be requested for a policy in force that is not renewed yet."
                )
            )
        template = self.env.ref("insurance_management.mail_template_policy_renewal_request")
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_composition_mode": "comment",
                "default_message_type": "comment",
                MAIL_KIND_CTX: "renewal_request",
            },
        }

    # -------------------------------------------------------------------------
    # Daily expiry process
    # -------------------------------------------------------------------------

    def _get_alert_subject(self, alert_type, days_left):
        """Subject of the internal alerts, in the rendering language."""
        self.ensure_one()
        number = self.policy_number or self.name
        branch = self.branch_id.name
        if alert_type == "expired":
            return self.env._("Policy %(number)s (%(branch)s) expired", number=number, branch=branch)
        if days_left == 0:
            return self.env._("Policy %(number)s (%(branch)s) expires today", number=number, branch=branch)
        if days_left == 1:
            return self.env._("Policy %(number)s (%(branch)s) expires tomorrow", number=number, branch=branch)
        return self.env._(
            "Policy %(number)s (%(branch)s) expires in %(days)s days",
            number=number,
            branch=branch,
            days=days_left,
        )

    def _get_record_url(self):
        """Link to the policy for internal users (handles login and company)."""
        self.ensure_one()
        return f"{self.get_base_url()}/mail/view?model={self._name}&res_id={self.id}"

    def _get_renewal_type_label(self):
        self.ensure_one()
        return dict(self._fields["renewal_type"]._description_selection(self.env)).get(
            self.renewal_type, ""
        )

    def _send_internal_alert(self, template, days_left):
        """Email ``template`` to every user to notify, one email per user in
        the user's own language. Returns the users actually emailed."""
        self.ensure_one()
        sent = self.env["res.users"]
        for user in self._get_notify_users():
            if not user.email:
                _logger.warning(
                    "Insurance alert for policy %s not sent to user %s: no email address",
                    self.id,
                    user.id,
                )
                continue
            template.with_context(
                insurance_recipient_lang=user.lang,
                insurance_recipient_name=user.name,
                insurance_days_left=days_left,
            ).send_mail(
                self.id,
                email_values={
                    "recipient_ids": [fields.Command.set(user.partner_id.ids)],
                    "email_to": False,
                },
            )
            sent |= user
        return sent

    def _log_alert(self, alert_type, today, thresholds, sent_threshold, recipients):
        """Record the alert rows: the threshold actually sent, and the larger
        thresholds crossed at the same time as covered."""
        self.ensure_one()
        self.env["insurance.policy.alert"].sudo().create(
            [
                {
                    "policy_id": self.id,
                    "alert_type": alert_type,
                    "threshold_days": threshold,
                    "date_to": self.date_to,
                    "sent_on": today,
                    "skipped": threshold != sent_threshold,
                    "recipient_ids": [fields.Command.set(recipients.ids)] if threshold == sent_threshold else [],
                }
                for threshold in thresholds
            ]
        )

    def _schedule_expiry_activity(self, days_left):
        """One open expiry activity per policy for the responsible: created
        once, then its deadline and summary follow the latest notice."""
        self.ensure_one()
        activity_type = self.env.ref("insurance_management.mail_activity_type_policy_expiry")
        # The daily process runs as a technical user: write the summary in
        # the responsible's own language.
        summary = self.with_context(lang=self.user_id.lang or self._get_chatter_lang())._get_alert_subject(
            "expiry_notice", days_left
        )
        activity = self.activity_ids.filtered(lambda a: a.activity_type_id == activity_type)[:1]
        if activity:
            activity.write({"summary": summary, "date_deadline": self.date_to, "user_id": self.user_id.id})
        else:
            self.activity_schedule(
                act_type_xmlid="insurance_management.mail_activity_type_policy_expiry",
                date_deadline=self.date_to,
                summary=summary,
                user_id=self.user_id.id,
            )

    def _get_chatter_lang(self):
        """Language of the notes the daily process logs in the chatter (read
        by everyone): the company's language."""
        self.ensure_one()
        return self.company_id.partner_id.lang or self.env.lang

    def _log_alert_note(self, alert_type, days_left, recipients):
        self.ensure_one()
        policy = self.with_context(lang=self._get_chatter_lang())
        if recipients:
            detail = policy.env._("Expiry notice sent to: %(users)s", users=", ".join(recipients.mapped("name")))
        else:
            detail = policy.env._(
                "Expiry notice not emailed: no user to notify has an email address. "
                "Check the users to notify of the settings, the branch and the policy."
            )
        policy._message_log(body=Markup("%s<br/>%s") % (policy._get_alert_subject(alert_type, days_left), detail))

    def _process_expiry_notice(self, today):
        """Send the expiry notice when a new threshold is reached.

        No exact-day match: every threshold already reached (days left lower
        or equal) and not yet notified for the current end date counts. When
        several are pending at once, only the one closest to the end date is
        sent and the larger ones are marked as covered. The end date itself
        (0 days) is an implicit last threshold ("expires today").
        """
        self.ensure_one()
        if self.state not in ACTIVE_STATES or self.renewed_by_id:
            return False
        days_left = (self.date_to - today).days
        if days_left < 0:
            return False
        thresholds = sorted(set(self._get_alert_days()) | {0}, reverse=True)
        done = set(
            self.alert_ids.filtered(
                lambda a: a.alert_type == "expiry_notice" and a.date_to == self.date_to
            ).mapped("threshold_days")
        )
        pending = [days for days in thresholds if days_left <= days and days not in done]
        if not pending:
            return False
        sent_threshold = min(pending)
        template = self.env.ref("insurance_management.mail_template_policy_expiry_notice")
        recipients = self._send_internal_alert(template, days_left)
        self._log_alert("expiry_notice", today, pending, sent_threshold, recipients)
        self._schedule_expiry_activity(days_left)
        self._log_alert_note("expiry_notice", days_left, recipients)
        return True

    def _process_expired_notice(self, today):
        """Send "Policy expired" once, when the policy ends without renewal."""
        self.ensure_one()
        if self.state not in ("expired", "not_renewed") or self.renewed_by_id:
            return False
        if self.alert_ids.filtered(lambda a: a.alert_type == "expired" and a.date_to == self.date_to):
            return False
        template = self.env.ref("insurance_management.mail_template_policy_expired")
        days_left = (self.date_to - today).days
        recipients = self._send_internal_alert(template, days_left)
        self._log_alert("expired", today, [0], 0, recipients)
        self._log_alert_note("expired", days_left, recipients)
        return True

    def _process_auto_non_renewal(self, today):
        """Send the non-renewal instruction automatically, once, the
        configured days before the end date."""
        self.ensure_one()
        if (
            self.state not in ACTIVE_STATES
            or self.renewal_type != "no_renew"
            or self.non_renewal_send_mode != "automatic"
            or self.non_renewal_sent_date
            or self.renewed_by_id
            or (self.date_to - today).days > self.non_renewal_days
        ):
            return False
        self._send_non_renewal_instruction(cc_responsible=True)
        return True

    def _process_expiry(self, today):
        """Daily step for one policy: state transition, then the emails."""
        self.ensure_one()
        previous_state = self.state
        self._apply_lifecycle_state(today)
        if self.state in ACTIVE_STATES:
            self._process_auto_non_renewal(today)
            self._process_expiry_notice(today)
        elif previous_state in CONFIRMED_STATES and self.state not in CONFIRMED_STATES:
            self._process_expired_notice(today)

    @api.model
    def _process_expiry_batch(self, policies, today=None):
        """Process ``policies`` one by one, each in its own savepoint: an
        error on one policy is logged and never stops the others.

        :return: the policies that failed.
        """
        today = today or self._get_today()
        failed = self.browse()
        for policy in policies:
            try:
                with self.env.cr.savepoint():
                    policy.with_company(policy.company_id)._process_expiry(today)
            except Exception:
                _logger.exception("Insurance expiry process failed for policy %s", policy.id)
                failed |= policy
        return failed

    @api.model
    def _cron_process_expiry(self):
        """Scheduled action: transitions and alerts of every confirmed policy
        (not started ones start on their start date), in batches of
        configurable size, committing after each batch."""
        today = self._get_today()
        batch_size = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "insurance_management.cron_batch_size", DEFAULT_BATCH_SIZE
            )
        ) or DEFAULT_BATCH_SIZE
        policies = self.sudo().search([("state", "in", CONFIRMED_STATES)], order="date_to, id")
        remaining = len(policies)
        for start in range(0, len(policies), batch_size):
            batch = policies[start:start + batch_size]
            self._process_expiry_batch(batch, today)
            remaining -= len(batch)
            self.env["ir.cron"]._commit_progress(len(batch), remaining=remaining)

    @api.model
    def action_print_policies_in_force(self):
        """Print the list of every policy in force of the allowed companies."""
        policies = self.search([("state", "in", ACTIVE_STATES)], order="date_to, id")
        if not policies:
            raise UserError(self.env._("There are no policies in force to print."))
        return self.env.ref("insurance_management.action_report_insurance_policy_list").report_action(policies)

    # -------------------------------------------------------------------------
    # Installments (Fase 2, stage b)
    # -------------------------------------------------------------------------

    def action_open_installment_generator(self, endorsement=None):
        self.ensure_one()
        if self.state == "cancelled":
            raise UserError(self.env._("Cancelled policies have no installments to generate."))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generate installments"),
            "res_model": "insurance.installment.generate",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_policy_id": self.id,
                "default_endorsement_id": endorsement.id if endorsement else False,
            },
        }

    def _is_historical_installment(self, number, due_date, endorsement=None, continue_from=1):
        """Installments before ``continue_from`` (running policy) or due before
        the go-live date are historical: paid before Odoo, never billed."""
        self.ensure_one()
        go_live = self.company_id.insurance_go_live_date
        return number < (continue_from or 1) or bool(
            go_live and not endorsement and due_date < go_live and self.in_progress
        )

    def _sync_historical_installments(self):
        """The running policy data changed after generating the installments:
        mark (or unmark) the policy installments as historical with the same
        rule as the generation. Billed or paid installments cannot change."""
        for policy in self:
            continue_from = policy.continue_from_installment if policy.in_progress else 1
            installments = policy.installment_ids.filtered(lambda i: not i.endorsement_id and not i.cancelled)
            changed = installments.filtered(
                lambda i: i.historical != policy._is_historical_installment(i.number, i.due_date, None, continue_from)
            )
            if not changed:
                continue
            blocked = changed.filtered(lambda i: i.move_id or i.payment_id)
            if blocked:
                raise UserError(
                    self.env._(
                        "Policy %(policy)s: installments %(installments)s are already billed or paid. Cancel "
                        "their bill (or payment) first, then change the running policy data.",
                        policy=policy.display_name,
                        installments=", ".join(blocked.sorted("number").mapped("name")),
                    )
                )
            to_mark = changed.filtered(lambda i: not i.historical)
            system = {"insurance_installment_system": True}
            to_mark.with_context(**system).write({"historical": True, "overdue": False})
            (changed - to_mark).with_context(**system).write({"historical": False})
            if to_mark:
                policy._message_log(
                    body=self.env._(
                        "Installments marked as historical (running policy): %(installments)s.",
                        installments=", ".join(to_mark.sorted("number").mapped("name")),
                    )
                )
            if changed - to_mark:
                policy._message_log(
                    body=self.env._(
                        "Installments no longer historical: %(installments)s.",
                        installments=", ".join((changed - to_mark).sorted("number").mapped("name")),
                    )
                )

    def _generate_installments(self, count, first_due_date, total_amount, payment_mode=None, endorsement=None, continue_from=1):
        """Create ``count`` monthly installments of equal amounts (the last
        one absorbs the rounding), replacing the ones not billed yet.

        Installments before ``continue_from`` (running policy) or due before
        the go-live date are historical: paid, without payment nor entry.
        """
        self.ensure_one()
        if count < 1:
            raise UserError(self.env._("Generate at least one installment."))
        if total_amount <= 0:
            raise UserError(
                self.env._("The total amount must be positive (refunds are handled with a credit note).")
            )
        Installment = self.env["insurance.installment"]
        existing = self.installment_ids.filtered(lambda i: i.endorsement_id == (endorsement or Installment.endorsement_id))
        if existing.filtered("is_locked"):
            raise UserError(
                self.env._("Some installments are already billed, paid or historical: they cannot be regenerated.")
            )
        existing.unlink()
        currency = self.currency_id
        base = currency.round(total_amount / count)
        values = []
        for index in range(count):
            number = index + 1
            amount = base if number < count else currency.round(total_amount - base * (count - 1))
            due_date = first_due_date + relativedelta(months=index)
            historical = self._is_historical_installment(number, due_date, endorsement, continue_from)
            values.append(
                {
                    "policy_id": self.id,
                    "endorsement_id": endorsement.id if endorsement else False,
                    "number": number,
                    "count": count,
                    "due_date": due_date,
                    "amount": amount,
                    "payment_mode_id": (payment_mode or self.payment_mode_id).id,
                    "historical": historical,
                }
            )
        installments = Installment.sudo().create(values).sudo(False)
        self._message_log(
            body=self.env._(
                "%(count)s installments generated%(endorsement)s.",
                count=count,
                endorsement=(" (" + endorsement.display_name + ")") if endorsement else "",
            )
        )
        return installments

    # -------------------------------------------------------------------------
    # Bills and credit notes (Fase 2, stage c)
    # -------------------------------------------------------------------------

    def _get_bill_line_account(self):
        """Account of the bill lines: the prepaid account with the module
        accrual, else the expense account (direct expense, and Enterprise
        deferred expenses, which keeps the expense account on the line)."""
        self.ensure_one()
        if self.accrual_method == "module":
            return self._get_prepaid_account()
        return self._get_expense_account()

    def _prepare_bill_line_vals(self, amount, label, date_from, date_to):
        """Values of the bill line: the insurance product (its taxes) on the
        premium share net of taxes, and the account of the accrual method.
        Hook for the bridge modules (e.g. Enterprise deferred dates)."""
        self.ensure_one()
        product = self._get_insurance_product()
        account = self._get_bill_line_account()
        if not account:
            raise UserError(
                self.env._(
                    "Policy %(policy)s: configure the insurance product and its expense account, or "
                    "the prepaid insurance account, in the insurance settings before creating bills.",
                    policy=self.display_name,
                )
            )
        policy = self.sudo()
        ratio = policy.premium / policy.premium_total if policy.premium and policy.premium_total else 1.0
        vals = {
            "name": label,
            "quantity": 1,
            "price_unit": self.currency_id.round(amount * ratio),
            "account_id": account.id,
            "analytic_distribution": self._get_analytic_distribution() or False,
        }
        if product:
            vals["product_id"] = product.id
        return vals

    def _prepare_bill_vals(self, move_type, amount, label, date_from, date_to, endorsement=None, installment=None):
        self.ensure_one()
        return {
            "move_type": move_type,
            "partner_id": self.insurer_id.id,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "ref": self.policy_number or self.name,
            "insurance_policy_id": self.id,
            "insurance_endorsement_id": endorsement.id if endorsement else False,
            "insurance_installment_id": installment.id if installment else False,
            "invoice_line_ids": [fields.Command.create(self._prepare_bill_line_vals(amount, label, date_from, date_to))],
        }

    def _create_bill(self, installments, endorsement=None):
        """Draft vendor bill of ``installments`` (one bill for all of them, or
        for a single one in billing mode per installment)."""
        self.ensure_one()
        installments = installments.filtered(lambda i: not i.historical and not i.cancelled and not i.move_id)
        if not installments:
            raise UserError(self.env._("There are no installments to bill."))
        amount = sum(installments.sudo().mapped("amount"))
        date_from = endorsement.effective_date if endorsement else self.date_from
        label = self.env._(
            "Insurance %(policy)s - %(branch)s %(period)s",
            policy=self.policy_number or self.name,
            branch=self.branch_id.name,
            period=f"{format_date(self.env, date_from)} - {format_date(self.env, self.date_to)}",
        )
        if endorsement:
            label = f"{label} ({endorsement.display_name})"
        single = installments if len(installments) == 1 and self.billing_mode == "installment" else None
        if single:
            label = f"{label} {single.name}"
        move = self.env["account.move"].create(
            self._prepare_bill_vals("in_invoice", amount, label, date_from, self.date_to, endorsement, single)
        )
        installments.with_context(insurance_installment_system=True).write({"move_id": move.id})
        return move

    def _create_credit_note(self, endorsement):
        self.ensure_one()
        amount = abs(endorsement.sudo().premium_difference)
        label = self.env._("Refund %(endorsement)s", endorsement=endorsement.display_name)
        return self.env["account.move"].create(
            self._prepare_bill_vals("in_refund", amount, label, endorsement.effective_date, self.date_to, endorsement)
        )

    def _action_view_moves(self, moves):
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_move_in_invoice_type")
        if len(moves) == 1:
            action.update({"view_mode": "form", "views": [(False, "form")], "res_id": moves.id})
        else:
            action["domain"] = [("id", "in", moves.ids)]
        return action

    def action_create_bill(self):
        """Bills of the policy installments, according to the billing mode."""
        self.ensure_one()
        installments = self.installment_ids.filtered(
            lambda i: not i.endorsement_id and not i.move_id and not i.historical and not i.cancelled
        )
        if not installments:
            if self.installment_ids.filtered(lambda i: not i.endorsement_id and i.move_id):
                raise UserError(
                    self.env._("All the installments of the policy already have a bill: see the Bills smart button.")
                )
            raise UserError(self.env._("Generate the installments first: there are none to bill."))
        moves = self.env["account.move"]
        if self.billing_mode == "installment":
            for installment in installments:
                moves |= self._create_bill(installment)
        else:
            moves = self._create_bill(installments)
        return self._action_view_moves(moves)

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_move_in_invoice_type")
        action["domain"] = [("insurance_policy_id", "=", self.id), ("move_type", "in", ("in_invoice", "in_refund"))]
        action["context"] = {"default_move_type": "in_invoice", "default_insurance_policy_id": self.id, "default_partner_id": self.insurer_id.id}
        return action

    def action_view_installments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_installment_action")
        action["domain"] = [("policy_id", "=", self.id)]
        action["context"] = {"default_policy_id": self.id}
        return action

    def action_generate_payments(self):
        """(Re)generate the payments of the installments ready to be paid by
        deferred check or scheduled transfer, and the automatic debits already
        due (what the daily process would pay, without waiting for it)."""
        self.ensure_one()
        Installment = self.env["insurance.installment"]
        payments = Installment._process_scheduled_payments(self.installment_ids)
        payments |= Installment._process_due_debits(self.installment_ids, self._get_today())
        if not payments:
            raise UserError(
                self.env._(
                    "No payment to generate: the installments need a posted bill and a deferred check or "
                    "scheduled transfer payment mode, or an automatic debit already due. Automatic debits "
                    "not due yet are paid by the daily process on their due date."
                )
            )
        return True

    # -------------------------------------------------------------------------
    # Accrual plan (Fase 2, stage d)
    # -------------------------------------------------------------------------

    @api.model
    def _get_months(self, date_from, date_to):
        """Last day of every month between both dates (both included)."""
        months = []
        current = date_utils.end_of(date_from, "month")
        last = date_utils.end_of(date_to, "month")
        while current <= last:
            months.append(current)
            current = date_utils.end_of(current + relativedelta(days=1), "month")
        return months

    def _create_accrual_lines(self, amount, date_from, date_to, endorsement=None, source_move=None):
        """Equal monthly parts of ``amount`` (company currency), the last one
        absorbing the rounding."""
        self.ensure_one()
        months = self._get_months(date_from, date_to)
        if not months or self.company_currency_id.is_zero(amount):
            return self.env["insurance.accrual.line"]
        currency = self.company_currency_id
        base = currency.round(amount / len(months))
        values = [
            {
                "policy_id": self.id,
                "endorsement_id": endorsement.id if endorsement else False,
                "source_move_id": source_move.id if source_move else False,
                "date": month,
                "amount": base if index < len(months) - 1 else currency.round(amount - base * (len(months) - 1)),
            }
            for index, month in enumerate(months)
        ]
        return self.env["insurance.accrual.line"].sudo().create(values)

    def _generate_accrual_plan(self, move):
        """Accrual plan of a posted bill or credit note (module accrual): the
        amount that went to the prepaid account, in company currency (at the
        rate of the document, RF-14), spread over the remaining validity."""
        self.ensure_one()
        if self.accrual_method != "module" or move.state != "posted":
            return self.env["insurance.accrual.line"]
        endorsement = move.insurance_endorsement_id
        if self.in_progress and not endorsement:
            # Running policy: its premium is accrued from the amount informed at
            # the go-live (action_generate_initial_accrual), never twice (RF-11).
            return self.env["insurance.accrual.line"]
        prepaid = self._get_prepaid_account()
        amount = sum(move.line_ids.filtered(lambda l: l.account_id == prepaid).mapped("balance"))
        existing = self.accrual_line_ids.filtered(lambda l: l.source_move_id == move)
        if existing.filtered("move_id"):
            # Posted again after a reset to draft with months already
            # accrued: keep the plan (its open lines stay editable).
            return self.env["insurance.accrual.line"]
        if existing:
            if not self.company_currency_id.compare_amounts(sum(existing.sudo().mapped("amount")), amount):
                return existing
            # Posted again with another amount: rebuild the plan.
            existing.sudo().unlink()
        date_from = endorsement.effective_date if endorsement else self.date_from
        return self._create_accrual_lines(amount, date_from, self.date_to, endorsement, move)

    def action_generate_initial_accrual(self):
        """Running policy (initial load): accrual plan of the amount still to
        accrue at the go-live, from the go-live month to the end date."""
        self.ensure_one()
        go_live = self.company_id.insurance_go_live_date
        if not self.in_progress or not go_live:
            raise UserError(self.env._("Only for running policies, with the go-live date set in the insurance settings."))
        initial = self.accrual_line_ids.filtered(lambda l: not l.source_move_id and not l.endorsement_id)
        if initial.filtered("move_id"):
            raise UserError(
                self.env._(
                    "The initial accrual plan already has accrued months: it can no longer be "
                    "generated again. Adjust its open months in the Accrual tab instead."
                )
            )
        # Generated again (e.g. after correcting the amount): it replaces the
        # previous plan, nothing was accrued yet.
        initial.sudo().unlink()
        lines = self._create_accrual_lines(self.sudo().unaccrued_amount, max(go_live, self.date_from), self.date_to)
        if not lines:
            raise UserError(self.env._("Enter the amount still to accrue at go-live first."))
        message = self.env._(
            "Initial accrual plan: %(months)s months, %(amount)s in total (see the Accrual tab).",
            months=len(lines),
            amount=format_amount(self.env, sum(lines.mapped("amount")), self.company_currency_id),
        )
        self._message_log(body=message)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": message,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def _close_accrual_plan(self, date):
        """Early end (cancellation): the months after ``date`` still to accrue
        are moved into the month of ``date``, so the rest is expensed at once.
        If the insurer refunds premium, the credit note reduces it."""
        self.ensure_one()
        period = date_utils.end_of(date, "month")
        future = self.accrual_line_ids.filtered(lambda l: not l.move_id and l.date > period)
        if not future:
            return
        amount = sum(future.sudo().mapped("amount"))
        future.unlink()
        self.env["insurance.accrual.line"].sudo().create(
            {"policy_id": self.id, "date": period, "amount": amount}
        )

    # -------------------------------------------------------------------------
    # Unpaid installments (Fase 2, stage f)
    # -------------------------------------------------------------------------

    def _get_mail_installment(self):
        """Installment rendered by the "overdue unpaid" email (from context)."""
        return self.env["insurance.installment"].sudo().browse(self.env.context.get("insurance_installment_id"))

    def _get_mail_installment_amount(self):
        """Formatted amount of that installment, only for recipients allowed
        to see amounts (empty otherwise)."""
        installment = self._get_mail_installment()
        if not installment or not self.env.context.get("insurance_show_amounts"):
            return ""
        return format_amount(self.env, installment.amount, installment.currency_id)

    def _get_unpaid_subject(self):
        installment = self._get_mail_installment()
        return self.env._(
            "Installment %(installment)s of policy %(number)s (%(branch)s) is overdue and unpaid",
            installment=installment.name,
            number=self.policy_number or self.name,
            branch=self.branch_id.name,
        )

    def _notify_unpaid_installment(self, installment):
        """Email "Overdue unpaid installment" to the responsible and the
        accounting users to notify, one email per user in their language."""
        self.ensure_one()
        template = self.env.ref("insurance_management.mail_template_installment_unpaid")
        users = (self.user_id | self.company_id.insurance_unpaid_notify_user_ids).filtered(
            lambda u: u.active and not u.share and u.email
        )
        for user in users:
            template.with_context(
                insurance_recipient_lang=user.lang,
                insurance_recipient_name=user.name,
                insurance_installment_id=installment.id,
                insurance_show_amounts=user.has_group(AMOUNTS_GROUP),
            ).send_mail(
                self.id,
                email_values={"recipient_ids": [fields.Command.set(user.partner_id.ids)], "email_to": False},
            )
        self.with_context(lang=self._get_chatter_lang())._message_log(
            body=self.with_context(lang=self._get_chatter_lang()).env._(
                "Installment %(installment)s is overdue and unpaid. Notified: %(users)s",
                installment=installment.name,
                users=", ".join(users.mapped("name")) or "-",
            )
        )
