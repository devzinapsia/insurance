from datetime import date

from odoo.tests import tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon


@tagged("post_install", "-at_install")
class TestOwnChecks(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        own_checks = cls.env.ref("l10n_latam_check.account_payment_method_own_checks")
        cls.check_line = cls.env["account.payment.method.line"].create(
            {
                "name": "Own checks",
                "payment_method_id": own_checks.id,
                "journal_id": cls.bank_journal.id,
                "payment_account_id": cls.outstanding.id,
            }
        )
        cls.check_mode = cls.env["insurance.payment.mode"].create(
            {
                "name": "Deferred check",
                "payment_type": "deferred_check",
                "payment_state": "draft",
                "journal_id": cls.bank_journal.id,
                "payment_method_line_id": cls.check_line.id,
            }
        )

    def test_deferred_check_per_installment(self):
        policy = self._policy(payment_mode_id=self.check_mode.id)
        installments = self._installments(policy, count=3)
        self._post_bill(policy)
        payments = installments.payment_id
        self.assertEqual(len(payments), 3, "One payment per installment when the bill is posted")
        for installment in installments:
            check = installment.payment_id.l10n_latam_new_check_ids
            self.assertEqual(len(check), 1)
            self.assertEqual(check.payment_date, installment.due_date)
            self.assertEqual(check.amount, installment.amount)
            self.assertEqual(installment.state, "scheduled")
        first = installments[0]
        first.payment_id.l10n_latam_new_check_ids.name = "00000123"
        first.payment_id.action_post()
        self.assertTrue(first.move_line_id.reconciled)
        self.assertEqual(first.state, "paid")
        self.assertEqual(first.payment_id.l10n_latam_new_check_ids.outstanding_line_id.date_maturity, date(self.year, 1, 1))

    def test_other_methods_without_checks(self):
        policy = self._policy(payment_mode_id=self.transfer_mode.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        self.assertFalse(installments.payment_id.l10n_latam_new_check_ids)
