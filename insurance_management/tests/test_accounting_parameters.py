from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountingParameters(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The accounting test user also manages insurance.
        cls.env.user.group_ids |= cls.env.ref("insurance_management.group_insurance_manager")
        cls.company = cls.company_data["company"]
        cls.expense_product_account = cls.company_data["default_account_expense"]
        cls.product = cls.env["product.product"].create(
            {
                "name": "Insurance premium",
                "type": "service",
                "purchase_ok": True,
                "property_account_expense_id": cls.expense_product_account.id,
            }
        )
        cls.prepaid = cls.env["account.account"].create(
            {"name": "Prepaid insurance", "code": "999902", "account_type": "asset_prepayments"}
        )
        cls.branch_expense = cls.copy_account(cls.expense_product_account)
        cls.policy_expense = cls.copy_account(cls.expense_product_account)
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.outstanding = cls.env["account.account"].create(
            {"name": "Outstanding payments", "code": "999901", "account_type": "asset_current", "reconcile": True}
        )
        cls.bank_journal.outbound_payment_method_line_ids[:1].payment_account_id = cls.outstanding
        cls.debit_mode = cls.env["insurance.payment.mode"].create(
            {
                "name": "Bank debit",
                "payment_type": "automatic_debit",
                "journal_id": cls.bank_journal.id,
                "payment_method_line_id": cls.bank_journal.outbound_payment_method_line_ids[:1].id,
            }
        )
        cls.company.write(
            {
                "insurance_product_id": cls.product.id,
                "insurance_prepaid_account_id": cls.prepaid.id,
                "insurance_billing_mode": "installment",
                "insurance_accrual_method": "none",
                "insurance_default_payment_mode_id": cls.debit_mode.id,
            }
        )
        Partner = cls.env["res.partner"]
        cls.insurer = Partner.create({"name": "Insurer SA", "is_insurer": True, "is_company": True})
        cls.producer = Partner.create({"name": "Producer", "is_insurance_producer": True})
        cls.branch = cls.env["insurance.branch"].create({"name": "Fleet", "object_type": "vehicle"})

    def _policy(self, **values):
        vals = {
            "policy_number": "ACC-1",
            "branch_id": self.branch.id,
            "insurer_id": self.insurer.id,
            "producer_id": self.producer.id,
            "date_from": date(2026, 1, 1),
            "date_to": date(2026, 12, 31),
            "company_id": self.company.id,
        }
        vals.update(values)
        return self.env["insurance.policy"].create(vals)

    def test_defaults_from_settings_and_branch(self):
        policy = self._policy()
        self.assertEqual(policy.billing_mode, "installment")
        self.assertEqual(policy.accrual_method, "none")
        self.assertEqual(policy.payment_mode_id, self.debit_mode)
        self.branch.billing_mode = "policy"
        self.assertEqual(self._policy(policy_number="ACC-2").billing_mode, "policy", "The branch wins over the settings")
        policy.billing_mode = "policy"
        self.assertEqual(policy.billing_mode, "policy", "Editable on the policy")

    def test_expense_account_hierarchy(self):
        policy = self._policy()
        self.assertEqual(policy._get_insurance_product(), self.product)
        self.assertEqual(policy._get_expense_account(), self.expense_product_account, "Product account")
        self.branch.expense_account_id = self.branch_expense
        self.assertEqual(policy._get_expense_account(), self.branch_expense, "Branch account")
        policy.expense_account_id = self.policy_expense
        self.assertEqual(policy._get_expense_account(), self.policy_expense, "Policy account")
        other_product = self.env["product.product"].create({"name": "Branch product", "type": "service", "purchase_ok": True})
        self.branch.product_id = other_product
        self.assertEqual(policy._get_insurance_product(), other_product)

    def test_prepaid_account_and_analytic(self):
        policy = self._policy()
        self.assertEqual(policy._get_prepaid_account(), self.prepaid)
        own = self.prepaid.copy({"code": "999903"})
        policy.prepaid_account_id = own
        self.assertEqual(policy._get_prepaid_account(), own)
        plan = self.env["account.analytic.plan"].create({"name": "Cost centers"})
        analytic = self.env["account.analytic.account"].create({"name": "Fleet", "plan_id": plan.id})
        self.branch.analytic_distribution = {str(analytic.id): 100}
        self.assertEqual(policy._get_analytic_distribution(), {str(analytic.id): 100})
        other = self.env["account.analytic.account"].create({"name": "Sales", "plan_id": plan.id})
        policy.analytic_distribution = {str(other.id): 100}
        self.assertEqual(policy._get_analytic_distribution(), {str(other.id): 100})

    def test_payment_mode_requires_outstanding_account(self):
        card = self.env["account.journal"].create({"name": "Card", "type": "credit", "code": "CARD"})
        method = card.outbound_payment_method_line_ids[:1]
        method.payment_account_id = False
        with self.assertRaises(ValidationError):
            self.env["insurance.payment.mode"].create(
                {"name": "Card debit", "payment_type": "automatic_debit", "journal_id": card.id, "payment_method_line_id": method.id}
            )
        method.payment_account_id = self.outstanding
        mode = self.env["insurance.payment.mode"].create(
            {"name": "Card debit", "payment_type": "automatic_debit", "journal_id": card.id, "payment_method_line_id": method.id, "payment_state": "posted"}
        )
        self.assertEqual(mode.payment_state, "posted")
        with self.assertRaises(ValidationError):
            mode.payment_method_line_id = self.bank_journal.outbound_payment_method_line_ids[:1]
        manual = self.env["insurance.payment.mode"].create({"name": "Manual", "payment_type": "manual"})
        self.assertFalse(manual.journal_id)

    def test_renewal_copies_accounting_parameters(self):
        policy = self._policy(billing_mode="policy", expense_account_id=self.policy_expense.id)
        policy.action_confirm()
        policy.with_context(insurance_lifecycle_write=True).write({"state": "expiring"})
        renewal = self.env["insurance.policy"].browse(policy.action_renew()["res_id"])
        self.assertEqual(
            (renewal.billing_mode, renewal.payment_mode_id, renewal.expense_account_id),
            ("policy", self.debit_mode, self.policy_expense),
        )

    def test_accounting_settings_only_for_accounting_administrators(self):
        insurance_admin = new_test_user(
            self.env, login="ins_admin_no_acc",
            groups="base.group_user,insurance_management.group_insurance_manager",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        settings = self.env["insurance.settings"].with_user(insurance_admin).with_company(self.company).create({"alert_days": "20"})
        settings.action_save()
        self.assertEqual(self.company.insurance_alert_days, "20")
        self.assertEqual(self.company.insurance_product_id, self.product, "Accounting setup untouched")
        accountant = new_test_user(
            self.env, login="ins_admin_acc",
            groups="base.group_user,insurance_management.group_insurance_manager,account.group_account_manager",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        settings = self.env["insurance.settings"].with_user(accountant).with_company(self.company).create({})
        self.assertEqual(settings.product_id, self.product)
        self.assertEqual(settings.default_payment_mode_id, self.debit_mode)
        settings.write({"billing_mode": "policy", "go_live_date": date(2026, 7, 1)})
        settings.action_save()
        self.assertEqual(self.company.insurance_billing_mode, "policy")
        self.assertEqual(self.company.insurance_go_live_date, date(2026, 7, 1))

    def test_settings_form_opens_with_users_to_notify(self):
        """The web client loads the settings through onchange: many2many
        defaults must be commands."""
        notify = new_test_user(self.env, login="ins_notify_form", groups="base.group_user")
        self.company.write({"insurance_notify_user_ids": notify.ids, "insurance_unpaid_notify_user_ids": notify.ids})
        form = Form(self.env["insurance.settings"].with_company(self.company))
        self.assertEqual(form.notify_user_ids[:], notify)
        self.assertEqual(form.unpaid_notify_user_ids[:], notify)

