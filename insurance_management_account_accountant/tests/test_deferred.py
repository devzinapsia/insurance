from datetime import date

from odoo.tests import tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon


@tagged("post_install", "-at_install")
class TestDeferredAccrual(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.deferred_account = cls.env["account.account"].create(
            {"name": "Deferred expense", "code": "999904", "account_type": "asset_current"}
        )
        cls.company.write(
            {
                "deferred_expense_account_id": cls.deferred_account.id,
                "generate_deferred_expense_entries_method": "on_validation",
                "insurance_accrual_method": "deferred",
            }
        )

    def test_bill_line_carries_deferral_dates(self):
        policy = self._policy()
        self.assertEqual(policy.accrual_method, "deferred", "Default of the settings")
        self._installments(policy, count=12)
        bill = self._post_bill(policy)
        line = bill.invoice_line_ids
        self.assertEqual(line.account_id, self.expense, "Deferred expenses keep the expense account")
        self.assertEqual((line.deferred_start_date, line.deferred_end_date), (date(self.year, 1, 1), date(self.year, 12, 31)))
        self.assertTrue(bill.deferred_move_ids, "Enterprise generated the deferral entries")
        self.assertFalse(policy.accrual_line_ids, "No module accrual plan")

    def test_endorsement_bill_deferred_from_effective_date(self):
        policy = self._policy()
        self._installments(policy, count=12)
        self._post_bill(policy)
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": policy.id,
                "type_id": self.env.ref("insurance_management.insurance_endorsement_type_data_change").id,
                "effective_date": date(self.year, 7, 1),
                "premium_difference": 60000.0,
                "description": "Premium adjustment",
            }
        )
        endorsement.action_confirm()
        policy._generate_installments(count=6, first_due_date=date(self.year, 7, 1), total_amount=60000.0, endorsement=endorsement)
        bill = self.env["account.move"].browse(endorsement.action_create_bill()["res_id"])
        self.assertEqual(bill.invoice_line_ids.deferred_start_date, date(self.year, 7, 1))
        self.assertEqual(bill.invoice_line_ids.deferred_end_date, date(self.year, 12, 31))

    def test_running_policy_deferred_from_go_live(self):
        self.company.insurance_go_live_date = date(self.year, 4, 1)
        policy = self._policy(in_progress=True, continue_from_installment=4)
        self._installments(policy, count=12, continue_from=4)
        bill = self._post_bill(policy, invoice_date=date(self.year, 4, 1))
        self.assertEqual(bill.amount_total, 900000.0)
        self.assertEqual(bill.invoice_line_ids.deferred_start_date, date(self.year, 4, 1))

    def test_other_methods_untouched(self):
        policy = self._policy(accrual_method="none")
        self._installments(policy, count=2)
        bill = self._post_bill(policy)
        self.assertFalse(bill.invoice_line_ids.deferred_start_date)
        self.assertFalse(bill.deferred_move_ids)
