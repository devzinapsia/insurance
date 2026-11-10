from datetime import date

from odoo import fields
from odoo.tests import tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon
from odoo.addons.insurance_management_account_payment_pro.hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestPaymentPro(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.use_payment_pro = True
        # Older open bill of the same insurer: account_payment_pro would pay
        # it first (oldest due date) if the debts were left auto-filled.
        cls.older_bill = cls.init_invoice(
            "in_invoice", partner=cls.insurer, invoice_date=date(cls.year - 1, 12, 1), amounts=[50000.0], post=True
        )

    def _assert_only_installment_paid(self, installment, payment):
        self.assertTrue(installment.move_line_id.reconciled, "The installment line is paid")
        self.assertEqual(installment.state, "paid")
        self.assertEqual(self.older_bill.payment_state, "not_paid", "Other bills of the insurer stay open")
        self.assertIn(installment.move_id, payment.reconciled_bill_ids, "The payment references its bill")

    def test_draft_payment_pays_its_installment_only(self):
        policy = self._policy(payment_mode_id=self.draft_debit_mode.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        first = installments[0]
        self.env["insurance.installment"]._process_daily_batch(first, first.due_date)
        payment = first.payment_id
        self.assertEqual(payment.state, "draft")
        self.assertEqual(payment.to_pay_move_line_ids, first.move_line_id, "Debts: the installment line only")
        self.assertEqual(payment.amount, first.amount)
        payment.action_post()
        self._assert_only_installment_paid(first, payment)
        self.assertFalse(installments[1].move_line_id.reconciled)

    def test_posted_debit_pays_its_installment_only(self):
        policy = self._policy(payment_mode_id=self.debit_mode.id)
        installments = self._installments(policy, count=2, first_due_date=date(self.year, 1, 10))
        self._post_bill(policy)
        first = installments[0]
        self.env["insurance.installment"]._process_daily_batch(installments, first.due_date)
        self.assertNotEqual(first.payment_id.state, "draft")
        self._assert_only_installment_paid(first, first.payment_id)
        self.assertFalse(installments[1].move_line_id.reconciled)

    def test_install_fixes_existing_draft_payments(self):
        policy = self._policy(payment_mode_id=self.draft_debit_mode.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        first = installments[0]
        self.env["insurance.installment"]._process_daily_batch(first, first.due_date)
        payment = first.payment_id
        # As left by account_payment_pro before this module: every open line.
        payment.action_add_all()
        self.assertIn(self.older_bill.line_ids.filtered("date_maturity"), payment.to_pay_move_line_ids)
        post_init_hook(self.env)
        self.assertEqual(payment.to_pay_move_line_ids, first.move_line_id)
        payment.action_post()
        self._assert_only_installment_paid(first, payment)

    def test_manual_payment_unchanged(self):
        """Payments not created for an installment keep the adhoc behaviour."""
        payment = self.env["account.payment"].create(
            {
                "payment_type": "outbound",
                "partner_type": "supplier",
                "partner_id": self.insurer.id,
                "amount": 10.0,
                "journal_id": self.bank_journal.id,
                "date": fields.Date.today(),
            }
        )
        self.assertIn(self.older_bill.line_ids.filtered("date_maturity"), payment.to_pay_move_line_ids)
