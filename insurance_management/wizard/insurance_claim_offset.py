from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount


class InsuranceClaimOffset(models.TransientModel):
    """Offset the claim receivable against debts, without money (section
    8.6): the unpaid premium the insurer discounts from the indemnity, or the
    bill of the workshop the insurer paid directly."""

    _name = "insurance.claim.offset"
    _description = "Offset an insurance claim"

    claim_id = fields.Many2one(comodel_name="insurance.claim", string="Claim", required=True, readonly=True)
    company_id = fields.Many2one(related="claim_id.company_id")
    currency_id = fields.Many2one(related="claim_id.company_currency_id")
    mode = fields.Selection(
        selection=[
            ("insurer", "Unpaid premium discounted by the insurer"),
            ("supplier", "Direct payment to the workshop or supplier"),
        ],
        string="Offset",
        required=True,
        default="insurer",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Creditor",
        compute="_compute_partner_id",
        help="Insurer (unpaid premium) or workshop / supplier of the claim (direct payment).",
    )
    line_ids = fields.Many2many(
        comodel_name="account.move.line",
        relation="insurance_claim_offset_line_rel",
        column1="offset_id",
        column2="line_id",
        string="Debts to offset",
        domain="[('partner_id', 'child_of', partner_id), ('company_id', '=', company_id), "
        "('account_id.account_type', '=', 'liability_payable'), ('parent_state', '=', 'posted'), "
        "('reconciled', '=', False), ('balance', '<', 0)]",
        help="Open payable items of the creditor. The oldest are offset first, up to the claim pending amount.",
    )
    claim_pending = fields.Monetary(
        string="Claim pending",
        currency_field="currency_id",
        compute="_compute_amounts",
        help="Pending part of the claim receivable, in company currency.",
    )
    debts_total = fields.Monetary(string="Selected debts", currency_field="currency_id", compute="_compute_amounts")
    amount = fields.Monetary(
        string="Amount to offset",
        currency_field="currency_id",
        compute="_compute_amounts",
        help="The lower of the claim pending amount and the selected debts.",
    )

    @api.depends("mode", "claim_id")
    def _compute_partner_id(self):
        for wizard in self:
            claim = wizard.claim_id
            wizard.partner_id = (
                claim.insurer_id.commercial_partner_id if wizard.mode == "insurer" else claim.supplier_id.commercial_partner_id
            )

    @api.depends("claim_id", "line_ids")
    def _compute_amounts(self):
        for wizard in self:
            line = wizard.claim_id.sudo().claim_line_id
            pending = line.amount_residual if line and not line.reconciled else 0.0
            debts = -sum(wizard.line_ids.mapped("amount_residual"))
            wizard.claim_pending = pending
            wizard.debts_total = debts
            wizard.amount = min(pending, debts)

    @api.onchange("mode")
    def _onchange_mode(self):
        self.line_ids = False

    def _check_installment_payments(self, lines):
        """An offset installment is paid by the offset: its generated payment
        must not pay it again. Draft payments are cancelled; a payment already
        posted blocks the offset."""
        installments = self.env["insurance.installment"].sudo().search([("move_line_id", "in", lines.ids)])
        cancelled = self.env["account.payment"]
        for installment in installments:
            payment = installment.payment_id
            if not payment or payment.state in ("canceled", "rejected"):
                continue
            if payment.state != "draft":
                raise UserError(
                    self.env._(
                        "Installment %(installment)s of policy %(policy)s already has the payment %(payment)s: "
                        "it cannot be offset with the claim.",
                        installment=installment.name,
                        policy=installment.policy_id.display_name,
                        payment=payment.display_name,
                    )
                )
            payment.action_cancel()
            cancelled |= payment
        return cancelled

    def action_confirm(self):
        self.ensure_one()
        claim = self.claim_id
        claim._check_accounting_access()
        claim.check_access("write")
        if self.mode == "supplier" and not claim.supplier_id:
            raise UserError(self.env._("Set the workshop or supplier of the claim first."))
        claim_line = claim.sudo().claim_line_id
        if claim.state != "approved" or not claim_line or claim_line.reconciled or claim.claim_type == "surety_execution":
            raise UserError(self.env._("Only an approved claim with an indemnity pending collection can be offset."))
        lines = self.line_ids.sorted(lambda l: (l.date_maturity or l.date, l.id))
        if not lines:
            raise UserError(self.env._("Choose the debts to offset."))
        currency = claim.company_currency_id
        remaining = self.amount
        if currency.is_zero(remaining):
            raise UserError(self.env._("There is nothing to offset."))
        cancelled = self._check_installment_payments(lines)
        ref = claim._get_entry_ref()
        line_vals = []
        used = self.env["account.move.line"]
        for debt in lines:
            if currency.is_zero(remaining):
                break
            amount = min(remaining, -debt.amount_residual)
            line_vals.append(
                Command.create(
                    {
                        "name": self.env._("%(ref)s: offset of %(debt)s", ref=ref, debt=debt.move_id.display_name),
                        "account_id": debt.account_id.id,
                        "partner_id": debt.partner_id.id,
                        "balance": amount,
                    }
                )
            )
            used |= debt
            remaining -= amount
        total = self.amount - remaining
        line_vals.append(
            Command.create(
                {
                    "name": self.env._("%(ref)s: claim offset", ref=ref),
                    "account_id": claim_line.account_id.id,
                    "partner_id": claim_line.partner_id.id,
                    "balance": -total,
                }
            )
        )
        move = self.env["account.move"].sudo().create(
            {
                "move_type": "entry",
                "journal_id": claim._get_claim_journal().id,
                "date": fields.Date.context_today(self),
                "ref": ref,
                "insurance_claim_id": claim.id,
                "line_ids": line_vals,
            }
        )
        move.action_post()
        for debt in used:
            (debt | move.line_ids.filtered(lambda l: l.account_id == debt.account_id and l.partner_id == debt.partner_id and l.balance > 0 and not l.reconciled)[:1]).reconcile()
        (claim_line | move.line_ids.filtered(lambda l: l.account_id == claim_line.account_id and l.balance < 0)).reconcile()
        body = self.env._(
            "Offset of %(amount)s against %(debts)s.",
            amount=format_amount(self.env, total, currency),
            debts=", ".join(used.move_id.mapped("display_name")),
        )
        if cancelled:
            body += " " + self.env._(
                "Draft payments cancelled: %(payments)s.", payments=", ".join(cancelled.mapped("display_name"))
            )
        claim._message_log(body=body)
        return {"type": "ir.actions.act_window_close"}
