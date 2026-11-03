import logging

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import format_date

from .insurance_tools import format_alert_days, parse_alert_days

_logger = logging.getLogger(__name__)

AMOUNTS_GROUP = "insurance_management.group_insurance_see_amounts"
# Policies the daily expiry process looks at.
ACTIVE_STATES = ("in_force", "expiring")
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
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
            if policy.state == "draft" or policy.company_id.insurance_duration_check != "block":
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

        In force until its end date (inclusive), Expiring from its first alert
        threshold. From the day after the end date, it ends as Renewed (a
        renewal exists), Not renewed (marked "do not renew") or Expired.
        """
        self.ensure_one()
        if self.state in UNCOVERED_STATES:
            return self.state
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

    def action_confirm(self):
        today = self._get_today()
        for policy in self:
            policy._check_can_confirm()
        for policy in self:
            issue = policy._get_duration_issue()
            policy.with_context(**{LIFECYCLE_CTX: True}).write({"state": "in_force"})
            if issue:
                policy._message_log(
                    body=self.env._("Confirmed with a duration warning: %(issue)s", issue=issue)
                )
        self._apply_lifecycle_state(today)
        return True

    def _check_can_reset_to_draft(self):
        """Hook for later phases (e.g. no linked invoices or payments)."""
        self.ensure_one()
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
        elif previous_state in ACTIVE_STATES:
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
        """Scheduled action: transitions and alerts of every active policy,
        in batches of configurable size, committing after each batch."""
        today = self._get_today()
        batch_size = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "insurance_management.cron_batch_size", DEFAULT_BATCH_SIZE
            )
        ) or DEFAULT_BATCH_SIZE
        policies = self.sudo().search([("state", "in", ACTIVE_STATES)], order="date_to, id")
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
