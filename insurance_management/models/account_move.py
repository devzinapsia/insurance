from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    insurance_policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Insurance policy",
        index="btree_not_null",
        copy=False,
        tracking=True,
        check_company=True,
        help="Insurance policy this bill belongs to.",
    )
    insurance_endorsement_id = fields.Many2one(
        comodel_name="insurance.endorsement",
        string="Insurance endorsement",
        index="btree_not_null",
        copy=False,
        domain="[('policy_id', '=', insurance_policy_id)]",
    )
    insurance_installment_id = fields.Many2one(
        comodel_name="insurance.installment",
        string="Insurance installment",
        index="btree_not_null",
        copy=False,
        domain="[('policy_id', '=', insurance_policy_id)]",
        help="Installment billed by this bill (billing mode one bill per installment).",
    )
    insurance_installment_ids = fields.One2many(
        comodel_name="insurance.installment",
        inverse_name="move_id",
        string="Insurance installments",
    )
    insurance_opening_debt = fields.Boolean(
        string="Insurance opening debt",
        copy=False,
        readonly=True,
        help="Bill bringing in the debt with the insurer of a running policy "
        "billed up front (initial load): it is not a new cost and is not accrued.",
    )
    insurance_accrual_date = fields.Date(
        string="Insurance accrual period",
        copy=False,
        readonly=True,
        help="Month (last day) of the insurance accrual entry.",
    )

    # One accrual entry per policy and month, enforced by the database.
    _insurance_accrual_uniq = models.UniqueIndex(
        "(insurance_policy_id, insurance_accrual_date) WHERE insurance_accrual_date IS NOT NULL AND state != 'cancel'",
        "There is already an accrual entry for this policy and month.",
    )

    # -------------------------------------------------------------------------
    # Posting
    # -------------------------------------------------------------------------

    def _post(self, soft=True):
        insurance_bills = self.filtered(
            lambda m: m.insurance_policy_id and m.move_type == "in_invoice" and m.state == "draft"
        )
        for bill in insurance_bills:
            bill._insurance_set_due_dates()
        posted = super()._post(soft)
        for move in posted.filtered(lambda m: m.insurance_policy_id and m.move_type in ("in_invoice", "in_refund")):
            move._insurance_after_post()
        return posted

    def button_draft(self):
        posted = self.filtered(
            lambda m: m.insurance_policy_id and m.move_type in ("in_invoice", "in_refund") and m.state == "posted"
        )
        res = super().button_draft()
        # The payable lines are rebuilt when the bill is posted again: the
        # installments are linked again then (and their payments reconciled).
        posted.insurance_installment_ids.with_context(insurance_installment_system=True).write(
            {"move_line_id": False}
        )
        return res

    def button_cancel(self):
        for move in self.filtered(lambda m: m.insurance_policy_id and m.move_type in ("in_invoice", "in_refund")):
            move._insurance_before_cancel()
        return super().button_cancel()

    def _insurance_before_cancel(self):
        """A cancelled bill no longer counts: its installments can be billed
        again and its accrual plan goes away (unless months were already
        accrued: then a credit note is the right correction)."""
        self.ensure_one()
        plan = self.env["insurance.accrual.line"].sudo().search([("source_move_id", "=", self.id)])
        if plan.filtered("move_id"):
            raise UserError(
                self.env._(
                    "Bill %(bill)s already has accrued months: issue a credit note instead of cancelling it.",
                    bill=self.display_name,
                )
            )
        plan.unlink()
        self.insurance_installment_ids.with_context(insurance_installment_system=True).write(
            {"move_id": False, "move_line_id": False}
        )

    def _insurance_get_installments(self):
        self.ensure_one()
        return self.insurance_installment_ids.filtered(lambda i: not i.historical and not i.cancelled).sorted(
            lambda i: (i.due_date, i.number, i.id)
        )

    def _insurance_set_due_dates(self):
        """One due date per installment: a payment term generated for the
        bill (N-1 percent lines + the remainder), so the payable lines match
        the installments whatever the final bill total is."""
        self.ensure_one()
        installments = self._insurance_get_installments()
        if not installments:
            return
        if not self.invoice_date:
            self.invoice_date = fields.Date.context_today(self)
        if len(installments) == 1:
            self.invoice_payment_term_id = False
            self.invoice_date_due = installments.due_date
            return
        precision = self.env["decimal.precision"].precision_get("Payment Terms")
        total = sum(installments.sudo().mapped("amount"))
        lines, allocated = [], 0.0
        for installment in installments[:-1]:
            percent = round(installment.sudo().amount * 100.0 / total, precision)
            allocated += percent
            lines.append(self._insurance_term_line(percent, installment.due_date))
        lines.append(self._insurance_term_line(round(100.0 - allocated, precision), installments[-1].due_date))
        previous = self.invoice_payment_term_id
        term = self.env["account.payment.term"].sudo().create(
            {
                "name": self.env._("%(policy)s installments", policy=self.insurance_policy_id.display_name),
                "company_id": self.company_id.id,
                "line_ids": lines,
            }
        )
        term.active = False
        self.invoice_payment_term_id = term
        # Posted again after a reset to draft: drop the term generated the
        # previous time if nothing else uses it.
        if previous and not previous.active and not self.search_count(
            [("invoice_payment_term_id", "=", previous.id)], limit=1
        ):
            previous.sudo().unlink()

    def _insurance_term_line(self, percent, due_date):
        return fields.Command.create(
            {
                "value": "percent",
                "value_amount": percent,
                "delay_type": "days_after",
                "nb_days": max((due_date - self.invoice_date).days, 0),
            }
        )

    def _insurance_after_post(self):
        """Link the payable lines to the installments, generate the scheduled
        payments, apply refunds and build the accrual plan."""
        self.ensure_one()
        if self.move_type == "in_invoice":
            installments = self._insurance_get_installments()
            payable = self.line_ids.filtered(lambda l: l.display_type == "payment_term").sorted(
                lambda l: (l.date_maturity, l.id)
            )
            if installments and len(payable) == len(installments):
                for installment, line in zip(installments, payable):
                    installment.with_context(insurance_installment_system=True).move_line_id = line
            # Posted again after a reset to draft: reconcile the payments
            # already posted, never generate them twice.
            for installment in installments.filtered("payment_id"):
                if installment.payment_id.state not in ("draft", "canceled", "rejected"):
                    installment._reconcile_with_payment(installment.payment_id)
            self.env["insurance.installment"]._process_scheduled_payments(installments)
        elif self.move_type == "in_refund" and self.insurance_endorsement_id.refund_mode == "installments":
            self._insurance_apply_refund_to_installments()
        self.insurance_policy_id._generate_accrual_plan(self)

    def _insurance_apply_refund_to_installments(self):
        """Deduct a refund from the next pending installments (nearest due
        date first) by reconciling the credit note with their payable lines."""
        self.ensure_one()
        refund_lines = self.line_ids.filtered(
            lambda l: l.display_type == "payment_term" and not l.reconciled
        )
        pending = self.insurance_policy_id.installment_ids.filtered(
            lambda i: i.move_line_id and not i.move_line_id.reconciled and i.state in ("pending", "scheduled", "overdue")
        ).sorted(lambda i: (i.due_date, i.id))
        for installment in pending:
            if all(line.reconciled for line in refund_lines):
                break
            (refund_lines.filtered(lambda l: not l.reconciled) + installment.move_line_id).reconcile()

    def action_open_insurance_policy(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "insurance.policy",
            "res_id": self.insurance_policy_id.id,
            "view_mode": "form",
        }

    @api.onchange("insurance_policy_id")
    def _onchange_insurance_policy_id(self):
        if self.insurance_policy_id and not self.partner_id:
            self.partner_id = self.insurance_policy_id.insurer_id


class AccountPayment(models.Model):
    _inherit = "account.payment"

    insurance_installment_id = fields.Many2one(
        comodel_name="insurance.installment",
        string="Insurance installment",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    insurance_policy_id = fields.Many2one(
        related="insurance_installment_id.policy_id",
        string="Insurance policy",
    )

    def action_post(self):
        res = super().action_post()
        # Draft payments generated for an installment are reconciled with it
        # when posted (modules such as account_payment_pro may have done it
        # already: then the line is reconciled and nothing happens).
        for payment in self.filtered("insurance_installment_id"):
            payment.insurance_installment_id._reconcile_with_payment(payment)
        return res
