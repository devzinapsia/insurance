import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import format_amount

from .insurance_policy import AMOUNTS_GROUP, CONFIRMED_STATES, DEFAULT_BATCH_SIZE

_logger = logging.getLogger(__name__)

CLAIM_TYPES = [
    ("own_damage", "Own damage"),
    ("theft", "Theft"),
    ("liability", "Civil liability (third-party claim)"),
    ("personal_accident", "Personal accident"),
    ("surety_execution", "Surety execution"),
]
# States the user moves the claim through (section 4.6). "Collected" is not
# here: it is derived from the reconciliation of the claim receivable line.
WORKFLOW_STATES = [
    ("draft", "Draft"),
    ("reported", "Reported"),
    ("analysis", "Under analysis"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("closed", "Closed"),
]
CLAIM_STATES = WORKFLOW_STATES[:4] + [("collected", "Collected")] + WORKFLOW_STATES[4:]
# A claim in these states still needs someone to move it.
OPEN_STATES = ("reported", "analysis", "approved")
# The claim was accepted by the insurer: its effect on the policy applies.
ACCEPTED_STATES = ("approved", "collected", "closed")
RECOVERY_DESTINATIONS = [
    ("company", "Payment to the company"),
    ("supplier", "Direct payment to the workshop or supplier"),
    ("replacement", "Replacement of the item"),
]
POLICY_EFFECTS = [
    ("none", "No effect"),
    ("reduce_sum", "Reduces the sum insured"),
    ("total_loss", "Total loss of the object"),
    ("surety_execution", "Surety execution"),
]
ACCOUNTING_GROUP = "account.group_account_invoice"


class InsuranceClaim(models.Model):
    """Claim filed with the insurer for a covered event (section 4.6, RF-12),
    with the accounting of the recovery (section 8.6)."""

    _name = "insurance.claim"
    _description = "Insurance claim"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_occurred desc, id desc"
    _rec_names_search = ["name", "insurer_claim_number"]
    _check_company_auto = True

    name = fields.Char(
        string="Reference",
        required=True,
        readonly=True,
        copy=False,
        index="trigram",
        default=lambda self: self.env._("New"),
    )
    insurer_claim_number = fields.Char(
        string="Insurer claim number",
        copy=False,
        tracking=True,
        help="Number the insurer assigns to the claim. It is also written on "
        "the approval entry, so the bank reconciliation finds the claim when "
        "the insurer quotes it on the transfer.",
    )
    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        ondelete="restrict",
        domain="[('state', 'not in', ('draft',))]",
    )
    object_id = fields.Many2one(
        comodel_name="insurance.policy.object",
        string="Affected object",
        index="btree_not_null",
        tracking=True,
        check_company=True,
        domain="[('policy_id', '=', policy_id)]",
        help="Insured object of the policy affected by the claim: a vehicle, a person or an item.",
    )
    insured_item_id = fields.Many2one(
        related="object_id.insured_item_id",
        store=True,
        index="btree_not_null",
        string="Insurable item",
    )
    company_id = fields.Many2one(related="policy_id.company_id", store=True, index=True, precompute=True)
    currency_id = fields.Many2one(related="policy_id.currency_id", store=True, precompute=True)
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
    branch_id = fields.Many2one(related="policy_id.branch_id", store=True, index=True, string="Branch")
    insurer_id = fields.Many2one(related="policy_id.insurer_id", store=True, index=True, string="Insurer")
    object_type = fields.Selection(related="policy_id.object_type")
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        required=True,
        index=True,
        tracking=True,
        default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
        help="Follows the claim and receives the reminders when it has no movement.",
    )
    claim_type = fields.Selection(
        selection=CLAIM_TYPES,
        string="Type",
        required=True,
        default="own_damage",
        tracking=True,
    )
    policy_effect = fields.Selection(
        selection=POLICY_EFFECTS,
        string="Effect on the policy",
        required=True,
        default="none",
        tracking=True,
        help="What the claim does to the policy once approved. No effect: "
        "the policy and the object stay the same. Reduces the sum insured: "
        "the indemnity is deducted from the sum available of the object, "
        "which can be rehabilitated with an endorsement. Total loss: the "
        "object is removed with an endorsement (the policy is cancelled when "
        "no object is left). Surety execution: the guarantee is executed and "
        "the policy ends.",
    )
    recovery_destination = fields.Selection(
        selection=RECOVERY_DESTINATIONS,
        string="Recovery destination",
        required=True,
        default="company",
        tracking=True,
        help="Payment to the company: the insurer pays the indemnity to the "
        "company. Direct payment to the workshop or supplier: the insurer pays "
        "the supplier and the claim is offset against the supplier bill, "
        "without money. Replacement: the insurer replaces the item, no entry "
        "is generated.",
    )
    workflow_state = fields.Selection(
        selection=WORKFLOW_STATES,
        string="Workflow status",
        required=True,
        default="draft",
        copy=False,
        readonly=True,
    )
    state = fields.Selection(
        selection=CLAIM_STATES,
        string="Status",
        compute="_compute_state",
        store=True,
        index=True,
        tracking=True,
        group_expand=True,
        help="Collected is set by itself when the indemnity is fully "
        "reconciled (bank reconciliation, a payment, an offset).",
    )

    # Dates -----------------------------------------------------------------------
    date_occurred = fields.Date(
        string="Date of occurrence",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_reported = fields.Date(string="Report date", tracking=True, copy=False)
    date_approved = fields.Date(string="Approval date", tracking=True, copy=False)
    date_collection_expected = fields.Date(
        string="Estimated collection date",
        tracking=True,
        copy=False,
        help="From the insurer's settlement or payment order. It is the due "
        "date of the claim receivable, so it shows in the aging and the cash "
        "forecast.",
    )
    date_collected = fields.Date(
        string="Collection date",
        compute="_compute_collection",
        store=True,
        help="Date of the last reconciliation that settled the indemnity.",
    )
    last_state_date = fields.Date(
        string="Last status change",
        default=fields.Date.context_today,
        copy=False,
        readonly=True,
    )
    stale_notified_on = fields.Date(string="Last reminder without movement", copy=False, readonly=True)
    is_stale = fields.Boolean(
        string="Without movement",
        compute="_compute_is_stale",
        search="_search_is_stale",
        help="Open claim whose status has not changed for the days set in the insurance settings.",
    )
    not_covered_warning = fields.Char(string="Coverage warning", compute="_compute_not_covered_warning")

    # Description ----------------------------------------------------------------
    location = fields.Char(string="Place")
    description = fields.Html(string="Account of the events")
    third_parties = fields.Text(string="Third parties involved")
    adjuster_id = fields.Many2one(comodel_name="res.partner", string="Adjuster", tracking=True)
    supplier_id = fields.Many2one(
        comodel_name="res.partner",
        string="Workshop or supplier",
        tracking=True,
        help="Repairs or replaces the damage. With direct payment, the claim "
        "is offset against its bill.",
    )
    note = fields.Html(string="Notes")

    # Amounts (in the policy currency) --------------------------------------------
    amount_estimated = fields.Monetary(
        string="Estimated damage", currency_field="currency_id", groups=AMOUNTS_GROUP, tracking=True
    )
    deductible_amount = fields.Monetary(
        string="Deductible",
        currency_field="currency_id",
        groups=AMOUNTS_GROUP,
        tracking=True,
        help="Part of the damage borne by the company. Informative: it is not "
        "posted, it stays as the net expense (repair bill minus the recovery).",
    )
    amount_claimed = fields.Monetary(
        string="Claimed", currency_field="currency_id", groups=AMOUNTS_GROUP, tracking=True
    )
    amount_approved = fields.Monetary(
        string="Approved",
        currency_field="currency_id",
        groups=AMOUNTS_GROUP,
        tracking=True,
        help="Indemnity settled by the insurer. It is the amount of the approval entry.",
    )
    amount_collected = fields.Monetary(
        string="Collected",
        currency_field="currency_id",
        groups=AMOUNTS_GROUP,
        compute="_compute_collection",
        store=True,
        help="Part of the approved indemnity already settled: collected, "
        "offset against debts, or closed with a difference.",
    )
    amount_pending = fields.Monetary(
        string="Pending collection",
        currency_field="currency_id",
        groups=AMOUNTS_GROUP,
        compute="_compute_collection",
        store=True,
    )
    amount_difference = fields.Monetary(
        string="Claimed minus collected",
        currency_field="currency_id",
        groups=AMOUNTS_GROUP,
        compute="_compute_collection",
        store=True,
    )

    # Accounting -------------------------------------------------------------------
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Approval entry",
        readonly=True,
        copy=False,
        index="btree_not_null",
    )
    claim_line_id = fields.Many2one(
        comodel_name="account.move.line",
        string="Claim journal item",
        readonly=True,
        copy=False,
        index="btree_not_null",
        help="Receivable from the insurer (or, for a surety execution, the "
        "debt with it) created by the approval entry.",
    )
    move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="insurance_claim_id",
        string="Journal entries",
    )
    move_count = fields.Integer(string="Journal entry count", compute="_compute_move_count")
    sum_rehabilitated = fields.Boolean(
        string="Sum insured rehabilitated",
        readonly=True,
        copy=False,
        help="A sum rehabilitation endorsement restored the sum insured this claim consumed.",
    )
    endorsement_ids = fields.One2many(
        comodel_name="insurance.endorsement",
        inverse_name="claim_id",
        string="Endorsements",
    )
    can_remove_object = fields.Boolean(compute="_compute_effect_actions")
    can_rehabilitate_sum = fields.Boolean(compute="_compute_effect_actions")
    can_insure_replacement = fields.Boolean(compute="_compute_effect_actions")
    attachment_ids = fields.One2many(
        comodel_name="ir.attachment",
        inverse_name="res_id",
        domain=[("res_model", "=", "insurance.claim")],
        string="Documents",
    )
    document_count = fields.Integer(string="Documents count", compute="_compute_document_count")

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends("name", "insurer_claim_number")
    def _compute_display_name(self):
        for claim in self:
            if claim.insurer_claim_number:
                claim.display_name = f"{claim.name} - {claim.insurer_claim_number}"
            else:
                claim.display_name = claim.name

    @api.depends(
        "workflow_state",
        "claim_type",
        "claim_line_id.reconciled",
        "claim_line_id.amount_residual_currency",
    )
    def _compute_state(self):
        for claim in self:
            line = claim.sudo().claim_line_id
            if (
                claim.workflow_state == "approved"
                and claim.claim_type != "surety_execution"
                and line
                and (line.reconciled or line.currency_id.is_zero(line.amount_residual_currency))
            ):
                claim.state = "collected"
            else:
                claim.state = claim.workflow_state

    @api.depends(
        "amount_approved",
        "amount_claimed",
        "claim_line_id.amount_residual_currency",
        "claim_line_id.reconciled",
        "claim_line_id.matched_credit_ids",
        "claim_line_id.matched_debit_ids",
    )
    def _compute_collection(self):
        for claim in self:
            claim = claim.sudo()
            line = claim.claim_line_id
            approved = claim.amount_approved if line else 0.0
            pending = abs(line.amount_residual_currency) if line and not line.reconciled else 0.0
            collected = approved - pending if line else 0.0
            claim.amount_pending = pending
            claim.amount_collected = collected
            claim.amount_difference = claim.amount_claimed - collected
            counterparts = line.matched_credit_ids.credit_move_id | line.matched_debit_ids.debit_move_id if line else line
            dates = counterparts.mapped("date") if line else []
            claim.date_collected = max(dates) if line and not pending and dates else False

    @api.depends("state", "last_state_date", "stale_notified_on", "company_id.insurance_claim_stale_days")
    @api.depends_context("insurance_today")
    def _compute_is_stale(self):
        today = self.env["insurance.policy"]._get_today()
        for claim in self:
            days = claim.company_id.insurance_claim_stale_days
            claim.is_stale = bool(
                days
                and claim.state in OPEN_STATES
                and claim.last_state_date
                and (today - claim.last_state_date).days >= days
            )

    def _search_is_stale(self, operator, value):
        if operator != "in":
            return NotImplemented
        today = self.env["insurance.policy"]._get_today()
        stale_ids = []
        for company in self.env.companies:
            days = company.insurance_claim_stale_days
            if not days:
                continue
            stale_ids += self.search(
                [
                    ("company_id", "=", company.id),
                    ("state", "in", OPEN_STATES),
                    ("last_state_date", "<=", today - timedelta(days=days)),
                ]
            ).ids
        stale = Domain("id", "in", stale_ids)
        if True in value and False in value:
            return Domain.TRUE
        return stale if True in value else ~stale

    @api.depends("policy_id", "date_occurred")
    def _compute_not_covered_warning(self):
        for claim in self:
            policy = claim.policy_id
            warning = False
            if policy and claim.date_occurred:
                if policy.state == "draft" or not policy.date_from or not policy.date_to:
                    warning = self.env._("The policy is not confirmed.")
                elif not policy.date_from <= claim.date_occurred <= policy.date_to and not policy._surety_is_open():
                    warning = self.env._(
                        "The policy was not in force on the date of occurrence (validity %(date_from)s - %(date_to)s).",
                        date_from=fields.Date.to_string(policy.date_from),
                        date_to=fields.Date.to_string(policy.date_to),
                    )
            claim.not_covered_warning = warning

    def _compute_move_count(self):
        for claim in self:
            claim.move_count = len(claim.sudo().move_ids)

    def _compute_document_count(self):
        counts = dict(
            self.env["ir.attachment"]._read_group(
                [("res_model", "=", self._name), ("res_id", "in", self.ids)],
                groupby=["res_id"],
                aggregates=["__count"],
            )
        )
        for claim in self:
            claim.document_count = counts.get(claim.id, 0)

    @api.depends("state", "policy_effect", "object_id.state", "policy_id.state", "endorsement_ids.state", "sum_rehabilitated")
    def _compute_effect_actions(self):
        for claim in self:
            accepted = claim.state in ACCEPTED_STATES
            policy_open = claim.policy_id.state in CONFIRMED_STATES
            pending_endorsement = claim.endorsement_ids.filtered(lambda e: e.state == "draft")
            claim.can_remove_object = bool(
                accepted
                and claim.policy_effect == "total_loss"
                and claim.object_id.state == "active"
                and policy_open
                and not pending_endorsement
            )
            claim.can_rehabilitate_sum = bool(
                accepted
                and claim.policy_effect == "reduce_sum"
                and claim.object_id.state == "active"
                and policy_open
                and not claim.sum_rehabilitated
                and not pending_endorsement
            )
            claim.can_insure_replacement = bool(accepted and claim.policy_effect == "total_loss")

    # -------------------------------------------------------------------------
    # Onchange / constraints
    # -------------------------------------------------------------------------

    @api.onchange("claim_type")
    def _onchange_claim_type(self):
        if self.claim_type == "surety_execution":
            self.policy_effect = "surety_execution"
        elif self.policy_effect == "surety_execution":
            self.policy_effect = "none"

    @api.onchange("policy_id")
    def _onchange_policy_id(self):
        if self.object_id and self.object_id.policy_id != self.policy_id:
            self.object_id = False
        if self.policy_id and not self.object_id:
            active = self.policy_id.object_ids.filtered(lambda o: o.state == "active")
            if len(active) == 1:
                self.object_id = active

    @api.constrains("claim_type", "policy_effect", "policy_id")
    def _check_surety(self):
        for claim in self:
            surety = claim.claim_type == "surety_execution" or claim.policy_effect == "surety_execution"
            if surety and (claim.claim_type != "surety_execution" or claim.policy_effect != "surety_execution"):
                raise ValidationError(
                    self.env._("A surety execution claim has the surety execution effect, and only it.")
                )
            if surety and claim.policy_id.object_type != "contract":
                raise ValidationError(
                    self.env._("Only surety bond policies (branch of type Contract) can be executed.")
                )

    @api.constrains("object_id", "policy_id")
    def _check_object(self):
        for claim in self:
            if claim.object_id and claim.object_id.policy_id != claim.policy_id:
                raise ValidationError(self.env._("The affected object must belong to the claim policy."))
            if claim.policy_effect in ("reduce_sum", "total_loss") and not claim.object_id:
                raise ValidationError(
                    self.env._("Choose the affected object: the effect on the policy applies to it.")
                )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model
    def _get_claim_sequence(self, company):
        """Claim reference sequence of ``company``, created on first use."""
        sequence = (
            self.env["ir.sequence"]
            .sudo()
            .search([("code", "=", "insurance.claim"), ("company_id", "=", company.id)], limit=1)
        )
        if not sequence:
            sequence = (
                self.env["ir.sequence"]
                .sudo()
                .create(
                    {
                        "name": f"Insurance claim ({company.name})",
                        "code": "insurance.claim",
                        "prefix": "SIN/%(range_year)s/",
                        "padding": 4,
                        "use_date_range": True,
                        "company_id": company.id,
                    }
                )
            )
        return sequence

    @api.model_create_multi
    def create(self, vals_list):
        default_name = self.env._("New")
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == default_name:
                policy = self.env["insurance.policy"].browse(vals.get("policy_id"))
                company = policy.company_id or self.env.company
                vals["name"] = self._get_claim_sequence(company).next_by_id(
                    sequence_date=vals.get("date_occurred")
                )
            if vals.get("claim_type") == "surety_execution":
                vals.setdefault("policy_effect", "surety_execution")
        return super().create(vals_list)

    def write(self, vals):
        if "workflow_state" in vals:
            vals.setdefault("last_state_date", self.env["insurance.policy"]._get_today())
        locked = self.filtered(lambda c: c.workflow_state in ("approved", "closed") and c.move_id)
        if locked and {"amount_approved", "policy_id", "claim_type"}.intersection(vals):
            raise UserError(
                self.env._(
                    "Claim %(claim)s already has its approval entry: cancel the approval to change "
                    "the approved amount, the policy or the type.",
                    claim=locked[0].display_name,
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_not_draft(self):
        if any(claim.workflow_state != "draft" for claim in self):
            raise UserError(self.env._("Only draft claims can be deleted."))

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _check_accounting_access(self):
        if not self.env.user.has_group(ACCOUNTING_GROUP):
            raise AccessError(
                self.env._("Only accounting users (Invoicing) can post the claim entries.")
            )

    def _get_claim_journal(self):
        self.ensure_one()
        journal = self.company_id.insurance_claim_journal_id
        if not journal:
            raise UserError(
                self.env._(
                    "Set the claims journal in the insurance settings (Accounting) before approving claims."
                )
            )
        return journal

    def _get_claim_account(self, branch_field, company_field, label):
        self.ensure_one()
        account = self.branch_id.sudo()[branch_field] or self.company_id[company_field]
        if not account:
            raise UserError(
                self.env._(
                    "Set the %(account)s in the insurance settings (Accounting) or in the branch "
                    "%(branch)s before approving claims.",
                    account=label,
                    branch=self.branch_id.display_name,
                )
            )
        return account

    def _get_entry_ref(self):
        """Reference of the claim entries: the internal number and the
        insurer's number as separate words, so Odoo's bank reconciliation
        matches a transfer quoting either of them."""
        self.ensure_one()
        if self.insurer_claim_number:
            return f"{self.name} - {self.insurer_claim_number}"
        return self.name

    def _line_amounts(self, amount, date):
        """Balance in company currency and amount in the claim currency."""
        self.ensure_one()
        balance = self.currency_id._convert(amount, self.company_currency_id, self.company_id, date)
        return balance, amount

    def _prepare_approval_move_vals(self):
        """Approval entry (section 8.6): debit the claims receivable (partner
        = insurer, due on the estimated collection date) against the
        recovery account. A surety execution debits the loss account against
        the debt with the insurer (section 4.6, the accounting is inverted)."""
        self.ensure_one()
        claim = self.sudo()
        date = claim.date_approved
        amount = claim.amount_approved
        balance, amount_currency = claim._line_amounts(amount, date)
        ref = claim._get_entry_ref()
        insurer = claim.insurer_id.commercial_partner_id
        maturity = claim.date_collection_expected or date
        if claim.claim_type == "surety_execution":
            debit_account = claim._get_claim_account(
                "surety_loss_account_id", "insurance_surety_loss_account_id", self.env._("surety execution loss account")
            )
            credit_account = insurer.with_company(claim.company_id).property_account_payable_id
            if not credit_account:
                raise UserError(self.env._("The insurer %(insurer)s has no payable account.", insurer=insurer.display_name))
            debit_vals = {"account_id": debit_account.id, "partner_id": insurer.id}
            credit_vals = {"account_id": credit_account.id, "partner_id": insurer.id, "date_maturity": maturity}
            if claim.policy_id.analytic_distribution:
                debit_vals["analytic_distribution"] = claim.policy_id.analytic_distribution
        else:
            debit_account = claim._get_claim_account(
                "claim_receivable_account_id", "insurance_claim_receivable_account_id", self.env._("claims receivable account")
            )
            credit_account = claim._get_claim_account(
                "claim_recovery_account_id", "insurance_claim_recovery_account_id", self.env._("claims recovery account")
            )
            debit_vals = {"account_id": debit_account.id, "partner_id": insurer.id, "date_maturity": maturity}
            credit_vals = {"account_id": credit_account.id, "partner_id": insurer.id}
            if claim.policy_id.analytic_distribution:
                credit_vals["analytic_distribution"] = claim.policy_id.analytic_distribution
        common = {"name": ref, "currency_id": claim.currency_id.id}
        return {
            "move_type": "entry",
            "journal_id": claim._get_claim_journal().id,
            "date": date,
            "ref": ref,
            "insurance_claim_id": claim.id,
            "line_ids": [
                Command.create({**common, **debit_vals, "balance": balance, "amount_currency": amount_currency}),
                Command.create({**common, **credit_vals, "balance": -balance, "amount_currency": -amount_currency}),
            ],
        }

    def _needs_approval_entry(self):
        self.ensure_one()
        claim = self.sudo()
        if claim.amount_approved <= 0:
            return False
        if claim.claim_type == "surety_execution":
            return True
        return claim.recovery_destination in ("company", "supplier")

    # -------------------------------------------------------------------------
    # Workflow
    # -------------------------------------------------------------------------

    def _check_state(self, allowed, action):
        for claim in self:
            if claim.workflow_state not in allowed:
                raise UserError(
                    self.env._(
                        "Claim %(claim)s cannot be %(action)s from its current status.",
                        claim=claim.display_name,
                        action=action,
                    )
                )

    def action_report(self):
        self._check_state(("draft",), self.env._("reported"))
        for claim in self:
            claim.write({"workflow_state": "reported", "date_reported": claim.date_reported or fields.Date.context_today(self)})
        return True

    def action_start_analysis(self):
        self._check_state(("reported",), self.env._("put under analysis"))
        self.write({"workflow_state": "analysis"})
        return True

    def action_reject(self):
        self._check_state(("draft", "reported", "analysis"), self.env._("rejected"))
        self.write({"workflow_state": "rejected"})
        return True

    def action_approve(self):
        """Approve the claim: post the approval entry when there is money
        involved, then apply the surety execution (the other effects are
        proposed with their own buttons)."""
        self._check_state(("reported", "analysis"), self.env._("approved"))
        for claim in self:
            claim.check_access("write")
            vals = {"workflow_state": "approved", "date_approved": claim.date_approved or fields.Date.context_today(self)}
            claim.write(vals)
            if claim._needs_approval_entry():
                claim._check_accounting_access()
                move = self.env["account.move"].sudo().create(claim._prepare_approval_move_vals())
                move.action_post()
                line = move.line_ids.filtered(
                    lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable")
                )[:1]
                claim.sudo().write({"move_id": move.id, "claim_line_id": line.id})
            if claim.policy_effect == "surety_execution":
                claim.policy_id._execute_surety(claim)
            claim._message_log(body=self.env._("Claim approved."))
        return True

    def action_cancel_approval(self):
        """Back to analysis: the approval entry is reversed. Only while the
        indemnity was not collected nor offset."""
        self._check_state(("approved",), self.env._("taken back to analysis"))
        for claim in self:
            claim._check_accounting_access()
            line = claim.sudo().claim_line_id
            if claim.state == "collected" or (line and (line.matched_debit_ids or line.matched_credit_ids)):
                raise UserError(
                    self.env._(
                        "Claim %(claim)s has collections or offsets: undo them before cancelling the approval.",
                        claim=claim.display_name,
                    )
                )
            if claim.policy_effect == "surety_execution":
                raise UserError(self.env._("A surety execution ends the policy: it cannot be taken back."))
            if claim.endorsement_ids.filtered(lambda e: e.state == "confirmed"):
                raise UserError(
                    self.env._("The effect of claim %(claim)s was already applied with an endorsement.", claim=claim.display_name)
                )
            move = claim.sudo().move_id
            if move and move.state == "posted":
                reversal = move._reverse_moves(
                    default_values_list=[{"date": fields.Date.context_today(self), "ref": claim._get_entry_ref()}],
                    cancel=True,
                )
                reversal.insurance_claim_id = claim
            claim.sudo().write({"workflow_state": "analysis", "move_id": False, "claim_line_id": False, "date_approved": False})
            claim._message_log(body=self.env._("Approval cancelled: the approval entry was reversed."))
        return True

    def action_close(self):
        """Close a collected, rejected or approved claim that leaves nothing
        to collect (e.g. replacement of the item, or a liability claim)."""
        for claim in self:
            line = claim.sudo().claim_line_id
            allowed = claim.state in ("collected", "rejected") or (
                claim.state == "approved" and (not line or line.reconciled or claim.claim_type == "surety_execution")
            )
            if not allowed:
                raise UserError(
                    self.env._(
                        "Claim %(claim)s still has an indemnity to collect: collect it, offset it or "
                        "close it with a difference.",
                        claim=claim.display_name,
                    )
                )
        self.write({"workflow_state": "closed"})
        return True

    def action_close_with_difference(self):
        """Collected less than approved: the pending part goes back to the
        recovery account and the claim is closed (section 8.6)."""
        self.ensure_one()
        self._check_accounting_access()
        self.check_access("write")
        claim = self.sudo()
        line = claim.claim_line_id
        if claim.state != "approved" or not line or line.reconciled or claim.claim_type == "surety_execution":
            raise UserError(self.env._("Only an approved claim with an indemnity pending collection can be closed with a difference."))
        date = fields.Date.context_today(self)
        recovery = claim._get_claim_account(
            "claim_recovery_account_id", "insurance_claim_recovery_account_id", self.env._("claims recovery account")
        )
        amount_currency = line.amount_residual_currency
        balance = line.amount_residual
        ref = claim._get_entry_ref()
        common = {"name": self.env._("%(ref)s: difference not collected", ref=ref), "currency_id": line.currency_id.id, "partner_id": line.partner_id.id}
        move = self.env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "journal_id": claim._get_claim_journal().id,
                "date": date,
                "ref": ref,
                "insurance_claim_id": claim.id,
                "line_ids": [
                    Command.create({**common, "account_id": recovery.id, "balance": balance, "amount_currency": amount_currency}),
                    Command.create({**common, "account_id": line.account_id.id, "balance": -balance, "amount_currency": -amount_currency}),
                ],
            }
        )
        move.action_post()
        (line | move.line_ids.filtered(lambda l: l.account_id == line.account_id)).reconcile()
        claim.write({"workflow_state": "closed"})
        claim._message_log(
            body=self.env._(
                "Closed with a difference of %(amount)s not collected.",
                amount=format_amount(self.env, abs(amount_currency), line.currency_id),
            )
        )
        return True

    def action_reopen(self):
        """Rejected or closed by mistake: back to analysis (only without
        accounting, which must be undone first)."""
        for claim in self:
            if claim.workflow_state not in ("rejected", "closed") or claim.sudo().move_id:
                raise UserError(
                    self.env._("Only rejected claims, or closed claims without entries, can be reopened.")
                )
        self.write({"workflow_state": "analysis"})
        return True

    def action_register_collection(self):
        """Register the collection of the indemnity on the claim receivable
        (when it is not collected from the bank reconciliation)."""
        self.ensure_one()
        self._check_accounting_access()
        line = self.sudo().claim_line_id
        if self.state != "approved" or not line or line.reconciled or self.claim_type == "surety_execution":
            raise UserError(self.env._("Only an approved claim with an indemnity pending collection can be collected."))
        return line.sudo(False).action_register_payment()

    def action_open_offset(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Offset the claim"),
            "res_model": "insurance.claim.offset",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_claim_id": self.id,
                "default_mode": "supplier" if self.recovery_destination == "supplier" else "insurer",
            },
        }

    # -------------------------------------------------------------------------
    # Effect on the policy (section 4.6)
    # -------------------------------------------------------------------------

    def _open_endorsement(self, endorsement):
        return {
            "type": "ir.actions.act_window",
            "res_model": "insurance.endorsement",
            "res_id": endorsement.id,
            "view_mode": "form",
            "target": "current",
        }

    def _get_effect_date(self):
        """Effective date of the effect endorsements: the occurrence, kept
        within the policy validity."""
        self.ensure_one()
        policy = self.policy_id
        return min(max(self.date_occurred, policy.date_from), policy.date_to)

    def action_remove_object(self):
        """Total loss: draft endorsement removing the object, with the claim
        as reason. Confirming it cancels the policy when no object is left."""
        self.ensure_one()
        if not self.can_remove_object:
            raise UserError(self.env._("The object of this claim cannot be removed now."))
        endorsement_type = self.env.ref("insurance_management.insurance_endorsement_type_remove_object")
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": self.policy_id.id,
                "type_id": endorsement_type.id,
                "effective_date": self._get_effect_date(),
                "claim_id": self.id,
                "description": self.env._("Total loss due to claim %(claim)s.", claim=self.display_name),
                "line_ids": [
                    Command.create(
                        {
                            "operation": "remove",
                            "object_id": self.object_id.id,
                            "reason": self.env._("Total loss (claim %(claim)s)", claim=self.name),
                        }
                    )
                ],
            }
        )
        return self._open_endorsement(endorsement)

    def action_rehabilitate_sum(self):
        """Reduced sum insured: draft endorsement increasing the object sum
        back to its sum insured (the premium difference is the insurer's)."""
        self.ensure_one()
        if not self.can_rehabilitate_sum:
            raise UserError(self.env._("The sum insured of this claim cannot be rehabilitated now."))
        endorsement_type = self.env.ref("insurance_management.insurance_endorsement_type_increase_sum")
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": self.policy_id.id,
                "type_id": endorsement_type.id,
                "effective_date": max(fields.Date.context_today(self), self.policy_id.date_from),
                "claim_id": self.id,
                "description": self.env._("Rehabilitation of the sum insured after claim %(claim)s.", claim=self.display_name),
                "line_ids": [
                    Command.create(
                        {
                            "operation": "change",
                            "object_id": self.object_id.id,
                            "sum_insured": self.object_id.sudo().sum_insured,
                        }
                    )
                ],
            }
        )
        return self._open_endorsement(endorsement)

    def action_insure_replacement(self):
        """Total loss: insure the replacement, as a new object of the same
        policy while it is in force, or as a new draft policy copied from it."""
        self.ensure_one()
        if not self.can_insure_replacement:
            raise UserError(self.env._("The replacement can only be insured after a total loss is approved."))
        policy = self.policy_id
        if policy.state in CONFIRMED_STATES:
            endorsement_type = self.env.ref("insurance_management.insurance_endorsement_type_add_object")
            endorsement = self.env["insurance.endorsement"].create(
                {
                    "policy_id": policy.id,
                    "type_id": endorsement_type.id,
                    "effective_date": min(max(fields.Date.context_today(self), policy.date_from), policy.date_to),
                    "claim_id": self.id,
                    "description": self.env._("Replacement of the object lost in claim %(claim)s.", claim=self.display_name),
                    "line_ids": [Command.create({"operation": "add", "name": self.env._("Replacement of %(object)s", object=self.object_id.name)})],
                }
            )
            return self._open_endorsement(endorsement)
        new_policy = policy._create_replacement_policy(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "insurance.policy",
            "res_id": new_policy.id,
            "view_mode": "form",
            "target": "current",
        }

    def _on_endorsement_confirmed(self, endorsement):
        """Hook of the effect endorsements: a rehabilitation restores the
        sum available; removing the last object cancels the policy."""
        self.ensure_one()
        if endorsement.kind == "increase_sum" and self.policy_effect == "reduce_sum":
            self.sudo().sum_rehabilitated = True
        if endorsement.kind == "remove_object" and self.policy_effect == "total_loss":
            policy = endorsement.policy_id
            if not policy.object_ids.filtered(lambda o: o.state == "active") and policy.state in CONFIRMED_STATES:
                policy._cancel_by_claim(self, endorsement.effective_date)

    # -------------------------------------------------------------------------
    # Views
    # -------------------------------------------------------------------------

    def action_view_moves(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("account.action_move_journal_line")
        action["domain"] = [("insurance_claim_id", "=", self.id)]
        action["context"] = {"create": False}
        return action

    def action_view_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "insurance_management.insurance_policy_document_action"
        )
        action["domain"] = [("res_model", "=", self._name), ("res_id", "=", self.id)]
        action["context"] = {"default_res_model": self._name, "default_res_id": self.id}
        return action

    def action_open_document_upload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Upload document"),
            "res_model": "insurance.policy.document.upload",
            "view_mode": "form",
            "target": "new",
            "context": {"default_claim_id": self.id},
        }

    def action_view_endorsements(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_endorsement_action")
        action["domain"] = [("claim_id", "=", self.id)]
        action["context"] = {}
        return action

    # -------------------------------------------------------------------------
    # Claims without movement (section 9)
    # -------------------------------------------------------------------------

    def _get_stale_subject(self):
        self.ensure_one()
        return self.env._(
            "Claim %(claim)s (policy %(policy)s) has had no movement for %(days)s days",
            claim=self.display_name,
            policy=self.policy_id.policy_number or self.policy_id.name,
            days=(self.env["insurance.policy"]._get_today() - self.last_state_date).days,
        )

    def _get_mail_amount(self, field_name):
        """Formatted amount for the reminder email, only for recipients
        allowed to see amounts (empty otherwise)."""
        self.ensure_one()
        if not self.env.context.get("insurance_show_amounts"):
            return ""
        return format_amount(self.env, self.sudo()[field_name], self.currency_id)

    def _get_record_url(self):
        self.ensure_one()
        return f"{self.get_base_url()}/mail/view?model={self._name}&res_id={self.id}"

    def _notify_stale(self, today):
        """Remind the responsible of an open claim without movement, once
        every "days without movement"."""
        self.ensure_one()
        days = self.company_id.insurance_claim_stale_days
        if not days or self.state not in OPEN_STATES:
            return False
        reference = max(filter(None, [self.last_state_date, self.stale_notified_on]))
        if (today - reference).days < days:
            return False
        user = self.user_id
        template = self.env.ref("insurance_management.mail_template_claim_stale")
        if user.email and user.active:
            template.with_context(
                insurance_recipient_lang=user.lang,
                insurance_recipient_name=user.name,
                insurance_show_amounts=user.has_group(AMOUNTS_GROUP),
            ).send_mail(
                self.id,
                email_values={"recipient_ids": [Command.set(user.partner_id.ids)], "email_to": False},
            )
        lang = self.policy_id._get_chatter_lang()
        claim = self.with_context(lang=lang)
        claim._message_log(
            body=Markup("%s<br/>%s")
            % (
                claim._get_stale_subject(),
                claim.env._("Reminder sent to: %(user)s", user=user.name)
                if user.email
                else claim.env._("Reminder not emailed: the responsible has no email address."),
            )
        )
        self.sudo().stale_notified_on = today
        return True

    @api.model
    def _cron_process_claims(self):
        """Scheduled action: reminders of the claims without movement, in
        batches committed one by one (idempotent within the same day)."""
        today = self.env["insurance.policy"]._get_today()
        batch_size = int(
            self.env["ir.config_parameter"].sudo().get_param("insurance_management.cron_batch_size", DEFAULT_BATCH_SIZE)
        ) or DEFAULT_BATCH_SIZE
        claims = self.sudo().search([("state", "in", OPEN_STATES)], order="id")
        remaining = len(claims)
        for start in range(0, len(claims), batch_size):
            batch = claims[start:start + batch_size]
            self._process_claims_batch(batch, today)
            remaining -= len(batch)
            self.env["ir.cron"]._commit_progress(len(batch), remaining=remaining)

    @api.model
    def _process_claims_batch(self, claims, today=None):
        today = today or self.env["insurance.policy"]._get_today()
        failed = self.browse()
        for claim in claims:
            try:
                with self.env.cr.savepoint():
                    claim.with_company(claim.company_id)._notify_stale(today)
            except Exception:
                _logger.exception("Insurance claim reminder failed for claim %s", claim.id)
                failed |= claim
        return failed
