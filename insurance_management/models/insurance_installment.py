import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

AMOUNTS_GROUP = "insurance_management.group_insurance_see_amounts"
INSTALLMENT_STATES = [
    ("pending", "Pending"),
    ("scheduled", "Scheduled"),
    ("paid", "Paid"),
    ("overdue", "Overdue unpaid"),
    ("cancelled", "Cancelled"),
]


class InsuranceInstallment(models.Model):
    """A part of the premium of a policy (or of an endorsement) with its due
    date and payment mode (section 4.5, RF-07)."""

    _name = "insurance.installment"
    _description = "Insurance installment"
    _order = "policy_id, endorsement_id, number, id"
    _check_company_auto = True

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        index=True,
        ondelete="cascade",
    )
    endorsement_id = fields.Many2one(
        comodel_name="insurance.endorsement",
        string="Endorsement",
        index="btree_not_null",
        ondelete="cascade",
        help="Set for the additional installments of an endorsement.",
    )
    company_id = fields.Many2one(related="policy_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="policy_id.currency_id", store=True, string="Currency")
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
    insurer_id = fields.Many2one(related="policy_id.insurer_id", store=True, string="Insurer")
    branch_id = fields.Many2one(related="policy_id.branch_id", store=True, string="Branch")
    number = fields.Integer(string="Number", required=True, default=1)
    count = fields.Integer(string="Of", help="Number of installments of the plan.")
    name = fields.Char(string="Installment", compute="_compute_name", store=True)
    due_date = fields.Date(string="Due date", required=True, index=True)
    amount = fields.Monetary(
        string="Amount",
        currency_field="currency_id",
        required=True,
        groups=AMOUNTS_GROUP,
    )
    amount_company = fields.Monetary(
        string="Amount in company currency",
        currency_field="company_currency_id",
        compute="_compute_amount_company",
        store=True,
        groups=AMOUNTS_GROUP,
        help="At the rate of the bill once billed; before, at the rate of the due date.",
    )
    payment_mode_id = fields.Many2one(
        comodel_name="insurance.payment.mode",
        string="Payment mode",
        check_company=True,
    )
    payment_type = fields.Selection(related="payment_mode_id.payment_type")
    historical = fields.Boolean(
        string="Historical",
        readonly=True,
        help="Installment due before the go-live (or before the installment "
        "a running policy continues from): recorded as paid, without payment "
        "nor journal entry.",
    )
    cancelled = fields.Boolean(string="Cancelled", readonly=True, copy=False)
    overdue = fields.Boolean(
        string="Overdue",
        readonly=True,
        copy=False,
        help="Set by the daily process when the due date passed without payment.",
    )
    overdue_notified = fields.Boolean(string="Overdue notified", readonly=True, copy=False)
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Bill",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    move_line_id = fields.Many2one(
        comodel_name="account.move.line",
        string="Payable line",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
        help="Line of the posted bill this installment pays.",
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Payment",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    amount_residual = fields.Monetary(
        string="Amount due",
        currency_field="currency_id",
        compute="_compute_amount_residual",
        groups=AMOUNTS_GROUP,
    )
    state = fields.Selection(
        selection=INSTALLMENT_STATES,
        string="Status",
        compute="_compute_state",
        store=True,
        index=True,
    )
    is_locked = fields.Boolean(string="Locked", compute="_compute_is_locked")

    _payment_uniq = models.UniqueIndex(
        "(payment_id) WHERE payment_id IS NOT NULL",
        "A payment can only pay one installment.",
    )

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------

    @api.depends("number", "count", "endorsement_id.name")
    def _compute_name(self):
        for installment in self:
            name = f"{installment.number}/{installment.count or installment.number}"
            if installment.endorsement_id:
                name = f"{installment.endorsement_id.name} {name}"
            installment.name = name

    @api.depends("amount", "due_date", "currency_id", "company_id", "move_line_id.balance")
    def _compute_amount_company(self):
        for installment in self:
            line = installment.sudo().move_line_id
            company = installment.company_id
            if line:
                installment.amount_company = abs(line.balance)
            elif installment.currency_id and company and installment.currency_id != company.currency_id:
                installment.amount_company = installment.currency_id._convert(
                    installment.amount, company.currency_id, company, installment.due_date or fields.Date.today()
                )
            else:
                installment.amount_company = installment.amount

    @api.depends("move_line_id.amount_residual_currency", "move_line_id.reconciled", "historical", "cancelled")
    def _compute_amount_residual(self):
        for installment in self:
            line = installment.sudo().move_line_id
            if installment.cancelled or installment.historical:
                installment.amount_residual = 0.0
            elif line:
                installment.amount_residual = abs(line.amount_residual_currency)
            else:
                installment.amount_residual = installment.sudo().amount

    @api.depends(
        "cancelled",
        "historical",
        "overdue",
        "payment_id",
        "payment_id.state",
        "move_line_id.reconciled",
        "move_line_id.amount_residual_currency",
    )
    def _compute_state(self):
        for installment in self:
            payment = installment.sudo().payment_id
            payment_active = payment and payment.state not in ("canceled", "rejected")
            line = installment.sudo().move_line_id
            if installment.cancelled:
                installment.state = "cancelled"
            elif installment.historical or (line and (line.reconciled or line.currency_id.is_zero(line.amount_residual_currency))):
                installment.state = "paid"
            elif installment.overdue:
                installment.state = "overdue"
            elif payment_active:
                installment.state = "scheduled"
            else:
                installment.state = "pending"

    @api.depends("move_id", "payment_id", "historical", "cancelled")
    def _compute_is_locked(self):
        for installment in self:
            installment.is_locked = bool(
                installment.move_id or installment.payment_id or installment.historical or installment.cancelled
            )

    # -------------------------------------------------------------------------
    # Constraints / CRUD
    # -------------------------------------------------------------------------

    @api.constrains("amount")
    def _check_amount(self):
        for installment in self.sudo():
            if installment.amount <= 0 and not installment.cancelled:
                raise ValidationError(self.env._("The amount of an installment must be positive."))

    def write(self, vals):
        locked_fields = {"amount", "due_date", "number", "policy_id", "endorsement_id"}
        if locked_fields.intersection(vals) and not self.env.context.get("insurance_installment_system"):
            locked = self.filtered("is_locked")
            if locked:
                raise UserError(
                    self.env._(
                        "Installment %(installment)s is already billed, paid or historical: its "
                        "amount and due date can no longer be changed.",
                        installment=locked[0].display_name,
                    )
                )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_locked(self):
        if any(installment.is_locked for installment in self):
            raise UserError(self.env._("Billed, paid or historical installments cannot be deleted."))

    # -------------------------------------------------------------------------
    # Payments (stage e)
    # -------------------------------------------------------------------------

    def _get_payment_values(self):
        """Values of the account.payment paying this installment."""
        self.ensure_one()
        mode = self.payment_mode_id
        line = self.move_line_id
        return {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": line.partner_id.id or self.policy_id.insurer_id.id,
            "amount": abs(line.amount_residual_currency),
            "currency_id": line.currency_id.id,
            "date": max(self.due_date, fields.Date.context_today(self)) if mode.payment_type == "automatic_debit" else self.due_date,
            "journal_id": mode.journal_id.id,
            "payment_method_line_id": mode.payment_method_line_id.id,
            "memo": f"{self.policy_id.policy_number or self.policy_id.name} {self.name}",
            "insurance_installment_id": self.id,
            "invoice_ids": [fields.Command.set(line.move_id.ids)],
        }

    def _can_generate_payment(self):
        self.ensure_one()
        return bool(
            self.state in ("pending", "overdue")
            and not self.payment_id
            and self.payment_mode_id
            and self.payment_mode_id.payment_type != "manual"
            and self.move_line_id
            and self.move_line_id.parent_state == "posted"
            and not self.move_line_id.reconciled
        )

    def _generate_payment(self):
        """Create the payment of the installment from its payment mode, and
        post it when the mode says so; otherwise it stays as a draft to review.
        Either way it is reconciled with the installment when posted (see
        account.payment.action_post). Bridge modules extend
        ``_get_payment_values`` (e.g. own deferred checks)."""
        self.ensure_one()
        if not self._can_generate_payment():
            return self.env["account.payment"]
        payment = self.env["account.payment"].create(self._get_payment_values())
        self.with_context(insurance_installment_system=True).payment_id = payment
        self._after_payment_created(payment)
        if self.payment_mode_id.payment_state == "posted":
            payment.action_post()
        return payment

    def _after_payment_created(self, payment):
        """Hook for bridge modules (e.g. own deferred checks)."""
        return True

    def _reconcile_with_payment(self, payment):
        """Reconcile the installment payable line with ``payment``."""
        self.ensure_one()
        line = self.move_line_id
        if not line or line.reconciled or not payment.move_id:
            return
        payment_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id == line.account_id and not l.reconciled
        )
        if payment_lines:
            (payment_lines + line).reconcile()

    @api.model
    def _process_scheduled_payments(self, installments):
        """Generate the future-dated payments of deferred check and scheduled
        transfer installments, each in its own savepoint."""
        created = self.env["account.payment"]
        for installment in installments.filtered(
            lambda i: i.payment_mode_id.payment_type in ("deferred_check", "scheduled_transfer")
        ):
            try:
                with self.env.cr.savepoint():
                    created |= installment._generate_payment()
            except Exception:
                _logger.exception("Insurance payment generation failed for installment %s", installment.id)
        return created

    # -------------------------------------------------------------------------
    # Daily process: automatic debits and overdue installments (stages e, f)
    # -------------------------------------------------------------------------

    @api.model
    def _process_daily_batch(self, installments, today):
        """Automatic debits due and overdue flags, one savepoint each.

        :return: installments that failed.
        """
        failed = self.browse()
        for installment in installments:
            try:
                with self.env.cr.savepoint():
                    installment.with_company(installment.company_id)._process_daily(today)
            except Exception:
                _logger.exception("Insurance installment process failed for installment %s", installment.id)
                failed |= installment
        return failed

    def _process_daily(self, today):
        self.ensure_one()
        if (
            self.payment_mode_id.payment_type == "automatic_debit"
            and self.due_date <= today
            and self._can_generate_payment()
        ):
            self._generate_payment()
        if self.state in ("pending", "scheduled") and self.due_date < today:
            self.with_context(insurance_installment_system=True).overdue = True
        if self.state == "overdue" and not self.overdue_notified:
            self.policy_id._notify_unpaid_installment(self)
            self.with_context(insurance_installment_system=True).overdue_notified = True

    @api.model
    def _cron_process_installments(self):
        today = fields.Date.context_today(self)
        batch_size = int(
            self.env["ir.config_parameter"].sudo().get_param("insurance_management.cron_batch_size", 200)
        ) or 200
        installments = self.sudo().search(
            [("state", "in", ("pending", "scheduled", "overdue")), ("historical", "=", False), ("due_date", "<=", today)],
            order="due_date, id",
        )
        remaining = len(installments)
        for start in range(0, len(installments), batch_size):
            batch = installments[start:start + batch_size]
            self._process_daily_batch(batch, today)
            remaining -= len(batch)
            self.env["ir.cron"]._commit_progress(len(batch), remaining=remaining)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_create_bill(self):
        """One bill per installment (billing mode per installment)."""
        policies = self.policy_id
        if len(policies) != 1:
            raise UserError(self.env._("Select installments of a single policy."))
        moves = self.env["account.move"]
        for installment in self.filtered(lambda i: not i.move_id and not i.historical and not i.cancelled):
            moves |= policies._create_bill(installment, endorsement=installment.endorsement_id)
        return policies._action_view_moves(moves)

    def action_generate_payment(self):
        payments = self.env["account.payment"]
        for installment in self:
            payments |= installment._generate_payment()
        if not payments:
            raise UserError(
                self.env._(
                    "No payment was generated: the installments need a posted bill, a payment "
                    "mode other than manual, and no payment yet."
                )
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", payments.ids)],
            "name": self.env._("Payments"),
        }


class InsuranceInstallmentGenerate(models.TransientModel):
    """Generate the installments of a policy or of an endorsement."""

    _name = "insurance.installment.generate"
    _description = "Generate insurance installments"

    policy_id = fields.Many2one(comodel_name="insurance.policy", required=True, readonly=True)
    endorsement_id = fields.Many2one(comodel_name="insurance.endorsement", readonly=True)
    currency_id = fields.Many2one(related="policy_id.currency_id")
    count = fields.Integer(string="Number of installments", required=True, default=12)
    first_due_date = fields.Date(string="First due date", required=True)
    total_amount = fields.Monetary(
        string="Total amount",
        currency_field="currency_id",
        required=True,
        groups=AMOUNTS_GROUP,
    )
    payment_mode_id = fields.Many2one(comodel_name="insurance.payment.mode", string="Payment mode")
    continue_from = fields.Integer(
        string="Continue from installment",
        default=1,
        help="Running policy loaded at go-live: the previous installments are "
        "created as historical (paid, without payments nor journal entries).",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        policy = self.env["insurance.policy"].browse(values.get("policy_id") or self.env.context.get("default_policy_id"))
        endorsement = self.env["insurance.endorsement"].browse(
            values.get("endorsement_id") or self.env.context.get("default_endorsement_id")
        )
        if policy:
            # Field defaults (12 installments, from 1) are replaced by the
            # policy values; explicit context defaults are kept.
            context = self.env.context
            start = endorsement.effective_date if endorsement else policy.date_from
            if start and policy.date_to and "default_count" not in context:
                months, days = policy._get_duration_parts(start, policy.date_to)
                values["count"] = max(months + (1 if days else 0), 1)
            values.setdefault("first_due_date", start)
            amount = endorsement.sudo().premium_difference if endorsement else policy.sudo().premium_total
            if "total_amount" in fields_list and self._has_field_access(self._fields["total_amount"], "read"):
                values.setdefault("total_amount", amount)
            values.setdefault("payment_mode_id", policy.payment_mode_id.id)
            if "default_continue_from" not in context:
                values["continue_from"] = 1 if endorsement else (policy.continue_from_installment or 1)
        return values

    def action_generate(self):
        self.ensure_one()
        self.policy_id._generate_installments(
            count=self.count,
            first_due_date=self.first_due_date,
            total_amount=self.sudo().total_amount,
            payment_mode=self.payment_mode_id,
            endorsement=self.endorsement_id,
            continue_from=self.continue_from,
        )
        return {"type": "ir.actions.act_window_close"}
