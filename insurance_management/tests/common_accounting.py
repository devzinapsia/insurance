from datetime import date

from odoo import fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class InsuranceAccountingCommon(AccountTestInvoicingCommon):
    """Company with the insurance accounting setup: insurance product (no
    taxes), prepaid account, accrual journal and one payment mode per type."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A policy of the current calendar year is always in force or expiring.
        cls.year = fields.Date.today().year
        cls.env.user.group_ids |= cls.env.ref("insurance_management.group_insurance_manager")
        cls.company = cls.company_data["company"]
        cls.expense = cls.company_data["default_account_expense"]
        cls.payable = cls.company_data["default_account_payable"]
        cls.product = cls.env["product.product"].create(
            {
                "name": "Insurance premium",
                "type": "service",
                "purchase_ok": True,
                "property_account_expense_id": cls.expense.id,
                "supplier_taxes_id": [],
            }
        )
        cls.prepaid = cls.env["account.account"].create(
            {"name": "Prepaid insurance", "code": "999902", "account_type": "asset_prepayments"}
        )
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.outstanding = cls.env["account.account"].create(
            {"name": "Outstanding payments", "code": "999901", "account_type": "asset_current", "reconcile": True}
        )
        cls.method_line = cls.bank_journal.outbound_payment_method_line_ids[:1]
        cls.method_line.payment_account_id = cls.outstanding
        PaymentMode = cls.env["insurance.payment.mode"]
        mode_vals = {"journal_id": cls.bank_journal.id, "payment_method_line_id": cls.method_line.id}
        cls.debit_mode = PaymentMode.create(
            {"name": "Bank debit", "payment_type": "automatic_debit", "payment_state": "posted", **mode_vals}
        )
        cls.draft_debit_mode = PaymentMode.create(
            {"name": "Bank debit (review)", "payment_type": "automatic_debit", "payment_state": "draft", **mode_vals}
        )
        cls.transfer_mode = PaymentMode.create(
            {"name": "Scheduled transfer", "payment_type": "scheduled_transfer", "payment_state": "draft", **mode_vals}
        )
        cls.manual_mode = PaymentMode.create({"name": "Manual", "payment_type": "manual"})
        cls.company.write(
            {
                "insurance_product_id": cls.product.id,
                "insurance_prepaid_account_id": cls.prepaid.id,
                "insurance_accrual_journal_id": cls.company_data["default_journal_misc"].id,
                "insurance_billing_mode": "policy",
                "insurance_accrual_method": "module",
                "insurance_default_payment_mode_id": cls.debit_mode.id,
            }
        )
        Partner = cls.env["res.partner"]
        cls.insurer = Partner.create({"name": "Insurer SA", "is_insurer": True, "is_company": True})
        cls.producer = Partner.create({"name": "Producer", "is_insurance_producer": True})
        cls.branch = cls.env["insurance.branch"].create({"name": "Fleet", "object_type": "vehicle"})

    def _policy(self, confirm=True, **values):
        vals = {
            "policy_number": "ACC-1",
            "branch_id": self.branch.id,
            "insurer_id": self.insurer.id,
            "producer_id": self.producer.id,
            "date_from": date(self.year, 1, 1),
            "date_to": date(self.year, 12, 31),
            "premium": 1200000.0,
            "premium_total": 1200000.0,
            "company_id": self.company.id,
        }
        vals.update(values)
        policy = self.env["insurance.policy"].create(vals)
        if confirm:
            policy.action_confirm()
        return policy

    def _installments(self, policy, count=12, total=None, **kwargs):
        return policy._generate_installments(
            count=count,
            first_due_date=kwargs.pop("first_due_date", policy.date_from),
            total_amount=total if total is not None else policy.premium_total,
            **kwargs,
        )

    def _post_bill(self, policy, invoice_date=None):
        invoice_date = invoice_date or date(self.year, 1, 1)
        action = policy.action_create_bill()
        bills = self.env["account.move"].browse(action.get("res_id")) or self.env["account.move"].search(action["domain"])
        bills.invoice_date = invoice_date
        bills.action_post()
        return bills

    def _amls(self, move, account):
        lines = move.line_ids.filtered(lambda l: l.account_id == account)
        return sum(lines.mapped("debit")), sum(lines.mapped("credit"))
