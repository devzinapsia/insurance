from odoo import api, fields, models
from odoo.exceptions import ValidationError

PAYMENT_TYPES = [
    ("automatic_debit", "Automatic debit"),
    ("deferred_check", "Deferred check or echeq"),
    ("scheduled_transfer", "Scheduled transfer"),
    ("manual", "Manual payment"),
]


class InsurancePaymentMode(models.Model):
    """A way of paying insurance installments, set up once by the
    administrator and chosen on each policy (and installment).

    It decides the journal and payment method of the generated payments and
    whether they are generated posted or as drafts to review.
    """

    _name = "insurance.payment.mode"
    _description = "Insurance payment mode"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name, id"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    payment_type = fields.Selection(
        selection=PAYMENT_TYPES,
        string="Payment type",
        required=True,
        default="automatic_debit",
        tracking=True,
        help="Automatic debit: the daily process generates the payment on the "
        "installment due date. Deferred check or echeq and scheduled transfer: "
        "the payments are generated with their future date when the "
        "installment plan is confirmed. Manual payment: no payment is "
        "generated, it is registered by hand.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Journal",
        check_company=True,
        tracking=True,
        domain="[('type', 'in', ('bank', 'cash', 'credit'))]",
        help="Bank, cash or credit card journal the payments are made from.",
    )
    payment_method_line_id = fields.Many2one(
        comodel_name="account.payment.method.line",
        string="Payment method",
        tracking=True,
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', 'outbound')]",
    )
    payment_state = fields.Selection(
        selection=[("posted", "Posted"), ("draft", "Draft (to review)")],
        string="Generated payment state",
        required=True,
        default="posted",
        tracking=True,
        help="Posted: the payment is posted and reconciled with the insurer "
        "bill right away. Draft: the payment waits for someone to review and "
        "post it; it is reconciled when posted.",
    )
    note = fields.Text(string="Notes")

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        if self.payment_method_line_id.journal_id != self.journal_id:
            self.payment_method_line_id = self.journal_id.outbound_payment_method_line_ids[:1]

    @api.constrains("payment_type", "journal_id", "payment_method_line_id")
    def _check_journal_setup(self):
        for mode in self:
            if mode.payment_type == "manual":
                continue
            if not mode.journal_id or not mode.payment_method_line_id:
                raise ValidationError(
                    self.env._(
                        "Payment mode %(mode)s: set the journal and the payment method.",
                        mode=mode.name,
                    )
                )
            if mode.payment_method_line_id.journal_id != mode.journal_id:
                raise ValidationError(
                    self.env._(
                        "Payment mode %(mode)s: the payment method does not belong to the journal.",
                        mode=mode.name,
                    )
                )
            if not mode.payment_method_line_id.payment_account_id:
                raise ValidationError(
                    self.env._(
                        "Payment mode %(mode)s: the payment method %(method)s of journal "
                        "%(journal)s has no outstanding payments account. Without it, "
                        "payments have no journal entry and cannot be reconciled with "
                        "the insurer bill. Set it in the journal (Outgoing payments tab).",
                        mode=mode.name,
                        method=mode.payment_method_line_id.name,
                        journal=mode.journal_id.name,
                    )
                )
