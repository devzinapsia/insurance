from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from odoo.tools import mute_logger

from .common_accounting import InsuranceAccountingCommon


@tagged("post_install", "-at_install")
class TestInstallments(InsuranceAccountingCommon):
    def test_equal_installments_last_absorbs_rounding(self):
        policy = self._policy(premium=1000.0, premium_total=1000.0)
        installments = self._installments(policy, count=3)
        self.assertEqual(installments.mapped("amount"), [333.33, 333.33, 333.34])
        self.assertEqual(installments.mapped("name"), ["1/3", "2/3", "3/3"])
        self.assertEqual(
            installments.mapped("due_date"),
            [date(self.year, 1, 1), date(self.year, 2, 1), date(self.year, 3, 1)],
        )
        self.assertEqual(set(installments.mapped("state")), {"pending"})
        self.assertEqual(installments.payment_mode_id, self.debit_mode, "Payment mode of the policy")
        self.assertEqual(policy.installment_count, 3)
        self.assertEqual(policy.installment_difference, 0.0)

    def test_installments_editable_until_billed(self):
        policy = self._policy()
        installments = self._installments(policy, count=2)
        # The insurer billed pro rata: the amounts are edited by hand.
        installments[0].amount = 700000.0
        installments[1].amount = 500000.0
        self.assertEqual(policy.installment_difference, 0.0)
        installments[0].amount = 600000.0
        self.assertEqual(policy.installment_difference, 100000.0, "The difference shows until it is fixed")
        with self.assertRaises(ValidationError):
            installments[0].amount = 0.0
        # Regenerating replaces the installments not billed yet.
        installments = self._installments(policy, count=4)
        self.assertEqual(policy.installment_count, 4)
        self._post_bill(policy)
        self.assertTrue(all(installments.mapped("is_locked")))
        with self.assertRaises(UserError):
            installments[0].amount = 1.0
        with self.assertRaises(UserError):
            installments[0].due_date = date(self.year, 6, 1)
        with self.assertRaises(UserError):
            self._installments(policy, count=12)
        with self.assertRaises(UserError):
            installments[0].unlink()
        # The payment mode can still change.
        installments[1].payment_mode_id = self.manual_mode

    def test_generator_wizard_defaults(self):
        policy = self._policy()
        action = policy.action_open_installment_generator()
        wizard = self.env[action["res_model"]].with_context(action["context"]).create({})
        self.assertEqual(wizard.count, 12)
        self.assertEqual(wizard.first_due_date, policy.date_from)
        self.assertEqual(wizard.total_amount, 1200000.0)
        self.assertEqual(wizard.payment_mode_id, self.debit_mode)
        wizard.count = 6
        wizard.action_generate()
        self.assertEqual(policy.installment_ids.mapped("amount"), [200000.0] * 6)

    def test_bill_per_policy_one_due_date_per_installment(self):
        policy = self._policy()
        installments = self._installments(policy, count=12)
        bill = self._post_bill(policy)
        self.assertEqual(len(bill), 1)
        self.assertEqual(bill.partner_id, self.insurer)
        self.assertEqual(bill.insurance_policy_id, policy)
        self.assertEqual(bill.amount_total, 1200000.0)
        payable = bill.line_ids.filtered(lambda l: l.display_type == "payment_term").sorted("date_maturity")
        self.assertEqual(len(payable), 12)
        self.assertEqual(payable.mapped("date_maturity"), installments.mapped("due_date"))
        self.assertEqual(installments.move_line_id, payable)
        for installment in installments:
            self.assertEqual(-installment.move_line_id.amount_currency, installment.amount)
        self.assertEqual(policy.invoice_count, 1)
        self.assertEqual(policy.amount_invoiced, 1200000.0)
        self.assertEqual(policy.amount_due, 1200000.0)

    def test_bill_per_installment(self):
        policy = self._policy(billing_mode="installment")
        installments = self._installments(policy, count=3)
        bills = self._post_bill(policy)
        self.assertEqual(len(bills), 3)
        for installment in installments:
            self.assertEqual(installment.move_id.insurance_installment_id, installment)
            self.assertEqual(installment.move_id.amount_total, installment.amount)
            self.assertEqual(installment.move_id.invoice_date_due, installment.due_date)
            self.assertTrue(installment.move_line_id)
        with self.assertRaises(UserError):
            policy.action_create_bill()

    def test_bill_line_premium_net_of_taxes(self):
        tax = self.env["account.tax"].create({"name": "VAT 21", "amount": 21.0, "type_tax_use": "purchase"})
        self.product.supplier_taxes_id = tax
        policy = self._policy(premium=1000.0, premium_total=1210.0)
        self._installments(policy, count=2)
        bill = self._post_bill(policy)
        self.assertEqual(bill.invoice_line_ids.price_unit, 1000.0)
        self.assertEqual(bill.amount_total, 1210.0)
        self.assertEqual(bill.line_ids.filtered(lambda l: l.display_type == "payment_term").mapped(lambda l: -l.amount_currency), [605.0, 605.0])

    def test_historical_installments(self):
        policy = self._policy()
        installments = self._installments(policy, count=12, continue_from=4)
        self.assertEqual(installments.filtered("historical").mapped("number"), [1, 2, 3])
        self.assertEqual(set(installments.filtered("historical").mapped("state")), {"paid"})
        bill = self._post_bill(policy)
        self.assertEqual(bill.amount_total, 900000.0, "Historical installments are not billed")
        self.assertEqual(len(bill.line_ids.filtered(lambda l: l.display_type == "payment_term")), 9)

    def test_insurance_user_without_accounting_rights(self):
        policy = self._policy()
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        user = new_test_user(
            self.env, login="ins_user_no_acc", groups="base.group_user,insurance_management.group_insurance_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        values = policy.with_user(user).read(["invoice_count", "installment_count", "has_debt", "amount_due"])[0]
        self.assertEqual((values["invoice_count"], values["installment_count"], values["amount_due"]), (1, 2, 1200000.0))
        rows = installments.with_user(user).read(["name", "state", "amount_residual", "payment_mode_id"])
        self.assertEqual([row["state"] for row in rows], ["pending", "pending"])
        with Form(policy.with_user(user)) as form:
            self.assertEqual(len(form.installment_ids), 2)
        # Cost report: amounts yes, the bill (accounting) not.
        Report = self.env["insurance.cost.report"].with_user(user)
        rows = Report.search_read([("policy_id", "=", policy.id)], ["amount", "branch_id", "insurer_id"])
        self.assertEqual(sum(row["amount"] for row in rows), 1200000.0)
        self.assertNotIn("move_id", Report.get_views([(False, "list")])["views"]["list"]["arch"])

    def test_bill_reset_to_draft_and_posted_again(self):
        policy = self._policy(payment_mode_id=self.transfer_mode.id)
        installments = self._installments(policy, count=3)
        bill = self._post_bill(policy)
        installments[0].payment_id.action_post()
        self.assertEqual(installments[0].state, "paid")
        plan = policy.accrual_line_ids
        self.assertEqual(len(plan), 12)
        bill.button_draft()
        self.assertFalse(installments.move_line_id, "Payable lines are rebuilt when posted again")
        self.assertEqual(installments.move_id, bill, "Still billed by the same bill")
        bill.action_post()
        self.assertEqual(len(installments.move_line_id), 3)
        self.assertTrue(installments[0].move_line_id.reconciled, "The posted payment is reconciled again")
        self.assertEqual(installments[0].state, "paid")
        self.assertEqual(len(installments.payment_id), 3, "No payment generated twice")
        self.assertEqual(policy.accrual_line_ids, plan, "Same amount: plan kept")
        # Corrected amount: the plan is rebuilt with it, never duplicated.
        bill.button_draft()
        bill.invoice_line_ids.price_unit = 1260000.0
        bill.action_post()
        self.assertEqual(len(policy.accrual_line_ids), 12)
        self.assertEqual(sum(policy.accrual_line_ids.mapped("amount")), 1260000.0)
        self.assertEqual(installments[0].payment_id.state, "in_process", "Payment kept, partially reconciled")

    def test_bill_cancelled_releases_installments(self):
        policy = self._policy(payment_mode_id=self.manual_mode.id)
        installments = self._installments(policy, count=3)
        bill = self._post_bill(policy)
        bill.button_draft()
        bill.button_cancel()
        self.assertFalse(installments.move_id)
        self.assertFalse(installments.move_line_id)
        self.assertFalse(policy.accrual_line_ids, "No accrual for a cancelled bill")
        self.assertEqual(set(installments.mapped("state")), {"pending"})
        installments[0].amount = 300000.0
        installments[1].amount = 500000.0
        new_bill = self._post_bill(policy)
        self.assertEqual(new_bill.amount_total, 1200000.0, "Billed again")
        self.assertEqual(installments.move_id, new_bill)

    def test_bill_with_posted_accrual_cannot_be_cancelled(self):
        policy = self._policy(payment_mode_id=self.manual_mode.id)
        self._installments(policy, count=3)
        bill = self._post_bill(policy)
        self.env["insurance.accrual.line"]._process_accrual_batch(policy.accrual_line_ids[:1])
        bill.button_draft()
        with self.assertRaises(UserError):
            bill.button_cancel()
        bill.action_post()
        self.assertEqual(len(policy.accrual_line_ids), 12, "Plan kept when months are already accrued")

    def test_reset_to_draft_blocked_by_posted_bill(self):
        policy = self._policy()
        self._installments(policy, count=2)
        self._post_bill(policy)
        with self.assertRaises(UserError):
            policy.action_reset_to_draft()


@tagged("post_install", "-at_install")
class TestInstallmentPayments(InsuranceAccountingCommon):
    def _today_after(self, installment):
        return installment.due_date + relativedelta(days=1)

    def test_automatic_debit_posted_and_reconciled(self):
        policy = self._policy()
        installments = self._installments(policy, count=3)
        self._post_bill(policy)
        first = installments[0]
        Installment = self.env["insurance.installment"]
        # Not due yet: nothing happens.
        Installment._process_daily_batch(installments, first.due_date - relativedelta(days=1))
        self.assertFalse(installments.payment_id)
        Installment._process_daily_batch(installments, first.due_date)
        self.assertTrue(first.payment_id)
        # Posted on the outstanding account: "in process" until the bank
        # statement is reconciled.
        self.assertIn(first.payment_id.state, ("in_process", "paid"))
        self.assertEqual(first.payment_id.amount, first.amount)
        self.assertEqual(first.payment_id.insurance_installment_id, first)
        self.assertTrue(first.move_line_id.reconciled)
        self.assertEqual(first.state, "paid")
        self.assertFalse(installments[1].payment_id, "Only the installment due")
        # Idempotent: a second run does not pay twice.
        payment = first.payment_id
        Installment._process_daily_batch(installments, first.due_date)
        self.assertEqual(first.payment_id, payment)
        self.assertEqual(self.env["account.payment"].search_count([("insurance_installment_id", "=", first.id)]), 1)
        # Debit (automatic debit, section 8.4): payable against the bank outstanding account.
        self.assertEqual(self._amls(payment.move_id, self.outstanding), (0.0, first.amount))

    def test_draft_payment_reconciled_when_posted(self):
        policy = self._policy(payment_mode_id=self.draft_debit_mode.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        first = installments[0]
        self.env["insurance.installment"]._process_daily_batch(first, first.due_date)
        payment = first.payment_id
        self.assertEqual(payment.state, "draft")
        self.assertEqual(first.state, "scheduled")
        payment.action_post()
        self.assertTrue(first.move_line_id.reconciled)
        self.assertEqual(first.state, "paid")
        self.assertEqual(installments[1].state, "pending")

    def test_scheduled_transfer_generated_when_bill_posted(self):
        policy = self._policy(payment_mode_id=self.transfer_mode.id)
        installments = self._installments(policy, count=3)
        self._post_bill(policy)
        self.assertEqual(len(installments.payment_id), 3)
        self.assertEqual(installments.payment_id.mapped("date"), installments.mapped("due_date"))
        self.assertEqual(set(installments.mapped("state")), {"scheduled"})
        with self.assertRaises(UserError):
            policy.action_generate_payments()

    def test_manual_installment_never_paid_automatically(self):
        policy = self._policy(payment_mode_id=self.manual_mode.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        self.env["insurance.installment"]._process_daily_batch(installments, installments[0].due_date)
        self.assertFalse(installments.payment_id)
        with self.assertRaises(UserError):
            installments.action_generate_payment()

    def test_manual_payment_from_the_bill_marks_installment_paid(self):
        policy = self._policy(payment_mode_id=self.manual_mode.id)
        installments = self._installments(policy, count=2)
        bill = self._post_bill(policy)
        self.env["account.payment.register"].with_context(
            active_model="account.move.line", active_ids=installments[0].move_line_id.ids
        ).create({"journal_id": self.bank_journal.id, "payment_method_line_id": self.method_line.id})._create_payments()
        self.assertEqual(installments[0].state, "paid")
        self.assertEqual(installments[1].state, "pending")
        self.assertEqual(policy.amount_paid, 600000.0)
        self.assertEqual(policy.amount_due, 600000.0)
        self.assertEqual(bill.payment_state, "partial")

    def test_overdue_installment_notified_once(self):
        accountant = self.env["res.users"].create(
            {"name": "Accountant", "login": "ins_acc_notify", "email": "accountant@example.com", "group_ids": [(4, self.env.ref("base.group_user").id)]}
        )
        self.company.insurance_unpaid_notify_user_ids = accountant
        policy = self._policy(payment_mode_id=self.manual_mode.id, user_id=accountant.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        first = installments[0]
        Mail = self.env["mail.mail"]
        domain = [("model", "=", "insurance.policy"), ("res_id", "=", policy.id), ("is_notification", "=", False)]
        before = Mail.search_count(domain)
        self.env["insurance.installment"]._process_daily_batch(installments, first.due_date)
        self.assertEqual(first.state, "pending", "Due today: not overdue yet")
        self.assertFalse(policy.has_debt)
        today = self._today_after(first)
        self.env["insurance.installment"]._process_daily_batch(installments, today)
        self.assertEqual(first.state, "overdue")
        self.assertTrue(first.overdue_notified)
        self.assertTrue(policy.has_debt)
        self.assertIn(policy, self.env["insurance.policy"].search([("has_debt", "=", True)]))
        self.assertEqual(Mail.search_count(domain), before + 1, "One email per user (responsible and accountant are the same)")
        mail = Mail.search(domain, order="id desc", limit=1)
        self.assertIn(accountant.partner_id, mail.recipient_ids)
        self.assertIn(first.name, mail.body_html)
        self.env["insurance.installment"]._process_daily_batch(installments, today)
        self.assertEqual(Mail.search_count(domain), before + 1, "Never notified twice")
        # Paid late: no more debt.
        self.env["account.payment.register"].with_context(
            active_model="account.move.line", active_ids=first.move_line_id.ids
        ).create({"journal_id": self.bank_journal.id, "payment_method_line_id": self.method_line.id})._create_payments()
        self.assertEqual(first.state, "paid")
        self.assertFalse(policy.has_debt)

    def test_unpaid_email_in_recipient_language(self):
        self.env["res.lang"]._activate_lang("es_AR")
        self.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        accountant = self.env["res.users"].create(
            {
                "name": "Contadora",
                "login": "ins_acc_es",
                "email": "contadora@example.com",
                "lang": "es_AR",
                "group_ids": [(4, self.env.ref("insurance_management.group_insurance_user").id)],
            }
        )
        policy = self._policy(payment_mode_id=self.manual_mode.id, user_id=accountant.id)
        installments = self._installments(policy, count=2)
        self._post_bill(policy)
        self.env["insurance.installment"]._process_daily_batch(installments, self._today_after(installments[0]))
        mail = self.env["mail.mail"].search(
            [("model", "=", "insurance.policy"), ("res_id", "=", policy.id), ("is_notification", "=", False)], limit=1
        )
        self.assertIn("vencida e impaga", mail.subject)
        self.assertIn("La siguiente cuota", mail.body_html)
        self.assertIn("600.000,00", mail.body_html, "Amount in the recipient format")
        for english in ("Installment", "What to do", "Due date", "You receive"):
            self.assertNotIn(english, mail.body_html)

    def test_cron_runs_in_batches(self):
        policy = self._policy()
        installments = self._installments(policy, count=2, first_due_date=date.today() - relativedelta(months=2))
        self._post_bill(policy, invoice_date=date.today() - relativedelta(months=2))
        # The commits of the cron are not allowed in tests: call the batch.
        failed = self.env["insurance.installment"]._process_daily_batch(installments, date.today())
        self.assertFalse(failed)
        self.assertEqual(set(installments.mapped("state")), {"paid"})


@tagged("post_install", "-at_install")
class TestAccrual(InsuranceAccountingCommon):
    def test_module_accrual_entries_section_8_4(self):
        """Bill 1,200,000 to prepaid insurance / payable, 100,000 per month
        expense / prepaid insurance."""
        policy = self._policy()
        self._installments(policy, count=12)
        bill = self._post_bill(policy)
        self.assertEqual(self._amls(bill, self.prepaid), (1200000.0, 0.0))
        self.assertEqual(self._amls(bill, self.payable), (0.0, 1200000.0))
        plan = policy.accrual_line_ids
        self.assertEqual(len(plan), 12)
        self.assertEqual(set(plan.mapped("amount")), {100000.0})
        self.assertEqual(plan[0].date, date(self.year, 1, 31))
        self.assertEqual(plan[-1].date, date(self.year, 12, 31))
        self.assertEqual(plan.source_move_id, bill)
        # Posting the same bill twice never duplicates the plan.
        policy._generate_accrual_plan(bill)
        self.assertEqual(len(policy.accrual_line_ids), 12)
        failed = self.env["insurance.accrual.line"]._process_accrual_batch(plan[:2])
        self.assertFalse(failed)
        entry = plan[0].move_id
        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.date, date(self.year, 1, 31))
        self.assertEqual(entry.insurance_accrual_date, date(self.year, 1, 31))
        self.assertEqual(self._amls(entry, self.expense), (100000.0, 0.0))
        self.assertEqual(self._amls(entry, self.prepaid), (0.0, 100000.0))
        self.assertEqual(plan[0].state, "posted")
        with self.assertRaises(UserError):
            plan[0].amount = 1.0
        # Idempotent: already posted lines are skipped.
        self.env["insurance.accrual.line"]._process_accrual_batch(plan[:2])
        self.assertEqual(self.env["account.move"].search_count([("insurance_policy_id", "=", policy.id), ("insurance_accrual_date", "!=", False)]), 2)

    def test_accrual_entry_in_company_language(self):
        self.env["res.lang"]._activate_lang("es_AR")
        self.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        self.company.partner_id.lang = "es_AR"
        policy = self._policy()
        self._installments(policy, count=12)
        self._post_bill(policy)
        line = policy.accrual_line_ids[0]
        self.env["insurance.accrual.line"].with_context(lang="en_US")._process_accrual_batch(line)
        self.assertIn("Devengamiento de seguro", line.move_id.ref)

    def test_accrual_lines_editable_before_posting(self):
        policy = self._policy()
        self._installments(policy, count=12)
        self._post_bill(policy)
        plan = policy.accrual_line_ids
        plan[0].amount = 150000.0
        plan[1].write({"amount": 50000.0, "date": date(self.year, 2, 10)})
        self.assertEqual(plan[1].date, date(self.year, 2, 28 if self.year % 4 else 29), "Normalized to month end")

    def test_direct_expense_without_accrual_plan(self):
        policy = self._policy(accrual_method="none")
        self._installments(policy, count=2)
        bill = self._post_bill(policy)
        self.assertEqual(self._amls(bill, self.expense), (1200000.0, 0.0))
        self.assertFalse(policy.accrual_line_ids)

    def test_missing_accrual_journal_does_not_stop_other_policies(self):
        policy = self._policy()
        self._installments(policy, count=12)
        self._post_bill(policy)
        other_company_setup = self.company.insurance_accrual_journal_id
        self.company.insurance_accrual_journal_id = False
        with mute_logger("odoo.addons.insurance_management.models.insurance_accrual"):
            failed = self.env["insurance.accrual.line"]._process_accrual_batch(policy.accrual_line_ids[:1])
        self.assertEqual(failed, policy.accrual_line_ids[:1])
        self.company.insurance_accrual_journal_id = other_company_setup
        self.assertFalse(self.env["insurance.accrual.line"]._process_accrual_batch(policy.accrual_line_ids[:1]))

    def test_entry_of_closed_period_goes_to_first_open_day(self):
        policy = self._policy()
        self._installments(policy, count=12)
        self._post_bill(policy)
        self.company.fiscalyear_lock_date = date(self.year, 2, 28)
        line = policy.accrual_line_ids[0]
        self.env["insurance.accrual.line"]._process_accrual_batch(line)
        self.assertEqual(line.move_id.date, date(self.year, 3, 1))
        self.assertEqual(line.move_id.insurance_accrual_date, date(self.year, 1, 31))

    def test_foreign_currency_accrues_at_bill_rate(self):
        foreign = self.setup_other_currency("EUR", rates=[(f"{self.year}-01-01", 0.001), (f"{self.year}-06-01", 0.0005)])
        policy = self._policy(currency_id=foreign.id, premium=1200.0, premium_total=1200.0)
        installments = self._installments(policy, count=12)
        bill = self._post_bill(policy)
        self.assertEqual(bill.currency_id, foreign)
        self.assertEqual(self._amls(bill, self.prepaid), (1200000.0, 0.0), "Company currency at the bill rate")
        self.assertEqual(set(policy.accrual_line_ids.mapped("amount")), {100000.0})
        self.assertEqual(installments[0].amount_residual, 100.0, "Installment residual in policy currency")
        self.assertEqual(installments[0].amount_company, 100000.0, "Company currency at the bill rate")
        rows = self.env["insurance.cost.report"].search([("policy_id", "=", policy.id)])
        self.assertEqual((sum(rows.mapped("amount")), sum(rows.mapped("amount_currency"))), (1200000.0, 1200.0))
        self.assertEqual((rows.branch_id, rows.insurer_id, rows.currency_id), (self.branch, self.insurer, foreign))

    def test_foreign_installment_paid_in_company_currency_exchange_difference(self):
        """RF-14: a foreign currency installment debited from a company
        currency journal is paid at the rate of the payment date, and the
        exchange difference is booked when reconciled."""
        foreign = self.setup_other_currency(
            "EUR", rates=[(f"{self.year - 1}-01-01", 0.001), (f"{self.year}-06-01", 0.0008)]
        )
        policy = self._policy(currency_id=foreign.id, premium=1200.0, premium_total=1200.0, date_from=date(self.year, 1, 1))
        installments = self._installments(policy, count=12)
        self._post_bill(policy)
        late = installments[-1]
        today = max(late.due_date, date.today())
        self.env["insurance.installment"]._process_daily_batch(late, today)
        payment = late.payment_id
        self.assertEqual(payment.journal_id.currency_id or self.company.currency_id, self.company.currency_id)
        self.assertEqual((payment.currency_id, payment.amount), (foreign, 100.0), "Installment amount in its currency")
        self.assertEqual(late.state, "paid")
        partials = late.move_line_id.matched_debit_ids
        self.assertTrue(partials.exchange_move_id, "Exchange difference booked on reconciliation")
        self.assertEqual(abs(payment.move_id.line_ids[:1].balance), 125000.0, "Rate of the payment date")

    def test_installment_company_amount_before_billing(self):
        foreign = self.setup_other_currency("EUR", rates=[(f"{self.year}-01-01", 0.001)])
        policy = self._policy(currency_id=foreign.id, premium=1200.0, premium_total=1200.0)
        installments = self._installments(policy, count=12)
        self.assertEqual(installments[0].amount_company, 100000.0, "At the rate of the due date")
        local = self._installments(self._policy(policy_number="ACC-2"), count=12)
        self.assertEqual(local[0].amount_company, 100000.0)

    def test_positive_endorsement_installments_and_bill(self):
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
        action = endorsement.action_open_installment_generator()
        wizard = self.env[action["res_model"]].with_context(action["context"]).create({})
        self.assertEqual((wizard.count, wizard.total_amount, wizard.first_due_date), (6, 60000.0, date(self.year, 7, 1)))
        wizard.action_generate()
        self.assertEqual(endorsement.installment_ids.mapped("amount"), [10000.0] * 6)
        self.assertTrue(endorsement.installment_ids[0].name.startswith(endorsement.name))
        self.assertEqual(policy.installment_difference, 0.0)
        bill_action = endorsement.action_create_bill()
        bill = self.env["account.move"].browse(bill_action["res_id"])
        bill.invoice_date = date(self.year, 7, 1)
        bill.action_post()
        self.assertEqual(bill.insurance_endorsement_id, endorsement)
        self.assertEqual(len(bill.line_ids.filtered(lambda l: l.display_type == "payment_term")), 6)
        plan = policy.accrual_line_ids.filtered(lambda l: l.endorsement_id == endorsement)
        self.assertEqual(len(plan), 6, "July to December")
        self.assertEqual(set(plan.mapped("amount")), {10000.0})

    def test_negative_endorsement_credit_note_deducted_from_installments(self):
        policy = self._policy(payment_mode_id=self.manual_mode.id)
        installments = self._installments(policy, count=12)
        self._post_bill(policy)
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": policy.id,
                "type_id": self.env.ref("insurance_management.insurance_endorsement_type_data_change").id,
                "effective_date": date(self.year, 7, 1),
                "premium_difference": -150000.0,
                "refund_mode": "installments",
                "description": "Lower premium",
            }
        )
        endorsement.action_confirm()
        refund = self.env["account.move"].browse(endorsement.action_create_bill()["res_id"])
        self.assertEqual(refund.move_type, "in_refund")
        refund.invoice_date = date(self.year, 7, 1)
        refund.action_post()
        self.assertEqual(installments[0].state, "paid", "Nearest installment fully covered by the refund")
        self.assertEqual(installments[1].amount_residual, 50000.0, "The rest deducted from the next one")
        self.assertEqual(refund.payment_state, "paid")
        with self.assertRaises(UserError):
            endorsement.action_create_bill()
        plan = policy.accrual_line_ids.filtered(lambda l: l.endorsement_id == endorsement)
        self.assertEqual(sum(plan.mapped("amount")), -150000.0, "Negative accrual of the refund")

    def test_cancellation_closes_plan_and_cancels_installments(self):
        policy = self._policy(payment_mode_id=self.manual_mode.id)
        installments = self._installments(policy, count=12)
        self._post_bill(policy)
        self.env["insurance.accrual.line"]._process_accrual_batch(policy.accrual_line_ids[:2])
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": policy.id,
                "type_id": self.env.ref("insurance_management.insurance_endorsement_type_cancellation").id,
                "effective_date": date(self.year, 4, 15),
            }
        )
        endorsement.action_confirm()
        self.assertEqual(policy.state, "cancelled")
        self.assertFalse(installments.filtered("cancelled"), "Billed installments stay (the bill is still owed)")
        open_lines = policy.accrual_line_ids.filtered(lambda l: not l.move_id)
        self.assertEqual(set(open_lines.mapped("date")), {date(self.year, 3, 31), date(self.year, 4, 30)})
        self.assertFalse(open_lines.filtered(lambda l: l.date > date(self.year, 4, 30)))
        self.assertEqual(sum(open_lines.mapped("amount")), 1000000.0, "The rest is expensed in the cancellation month")


@tagged("post_install", "-at_install")
class TestInitialLoad(InsuranceAccountingCommon):
    def test_running_policy_initial_accrual(self):
        self.company.insurance_go_live_date = date(self.year, 4, 1)
        policy = self._policy(in_progress=True, continue_from_installment=4, unaccrued_amount=900000.0)
        action = policy.action_open_installment_generator()
        wizard = self.env[action["res_model"]].with_context(action["context"]).create({})
        self.assertEqual(wizard.continue_from, 4)
        wizard.action_generate()
        installments = policy.installment_ids
        self.assertEqual(installments.filtered("historical").mapped("number"), [1, 2, 3])
        bill = self._post_bill(policy, invoice_date=date(self.year, 4, 1))
        self.assertEqual(bill.amount_total, 900000.0)
        self.assertFalse(policy.accrual_line_ids, "The bill of a running policy does not accrue twice")
        policy.action_generate_initial_accrual()
        plan = policy.accrual_line_ids
        self.assertEqual(len(plan), 9, "April to December")
        self.assertEqual(sum(plan.mapped("amount")), 900000.0)
        self.assertEqual(plan[0].date, date(self.year, 4, 30))
        with self.assertRaises(UserError):
            policy.action_generate_initial_accrual()
        # Historical installments never generate payments.
        self.env["insurance.installment"]._process_daily_batch(installments, date(self.year, 12, 31))
        self.assertFalse(installments.filtered("historical").payment_id)

    def test_go_live_date_marks_previous_installments_historical(self):
        self.company.insurance_go_live_date = date(self.year, 3, 15)
        policy = self._policy(in_progress=True)
        installments = self._installments(policy, count=12)
        self.assertEqual(installments.filtered("historical").mapped("number"), [1, 2, 3])
        regular = self._policy(policy_number="ACC-2")
        self.assertFalse(self._installments(regular, count=12).filtered("historical"), "Only running policies")
