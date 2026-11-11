from datetime import date, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common_accounting import InsuranceAccountingCommon


class InsuranceClaimCommon(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.claims_receivable = cls.env["account.account"].create(
            {"name": "Claims receivable", "code": "999910", "account_type": "asset_receivable", "reconcile": True}
        )
        cls.recovery = cls.env["account.account"].create(
            {"name": "Claims recovery", "code": "999911", "account_type": "income_other"}
        )
        cls.surety_loss = cls.env["account.account"].create(
            {"name": "Surety execution loss", "code": "999912", "account_type": "expense"}
        )
        cls.claims_journal = cls.env["account.journal"].create(
            {"name": "Claims", "code": "SIN", "type": "general", "company_id": cls.company.id}
        )
        cls.company.write(
            {
                "insurance_claim_journal_id": cls.claims_journal.id,
                "insurance_claim_receivable_account_id": cls.claims_receivable.id,
                "insurance_claim_recovery_account_id": cls.recovery.id,
                "insurance_surety_loss_account_id": cls.surety_loss.id,
            }
        )
        cls.workshop = cls.env["res.partner"].create({"name": "Workshop SA", "is_company": True})
        cls.Claim = cls.env["insurance.claim"]

    def _vehicle_policy(self, objects=1, **values):
        values.setdefault(
            "object_ids",
            [Command.create({"name": f"Truck {i}", "license_plate": f"AB{i:03d}CD", "sum_insured": 1000000}) for i in range(objects)],
        )
        return self._policy(**values)

    def _claim(self, policy, obj=None, **values):
        vals = {
            "policy_id": policy.id,
            "object_id": (obj or policy.object_ids[:1]).id,
            "date_occurred": date(self.year, 3, 10),
            "amount_claimed": 500000,
            "amount_approved": 450000,
            "deductible_amount": 50000,
            "date_collection_expected": date(self.year, 4, 30),
            "insurer_claim_number": "INS778899",
        }
        vals.update(values)
        claim = self.Claim.create(vals)
        claim.action_report()
        return claim

    def _claim_line(self, claim):
        return claim.move_id.line_ids.filtered(lambda l: l.account_id == self.claims_receivable)

    def _collect(self, claim, amount=None):
        action = claim.action_register_collection()
        self.assertEqual(action["res_model"], "account.payment.register")
        wizard = self.env["account.payment.register"].with_context(**action["context"]).create(
            {"journal_id": self.bank_journal.id, "payment_date": date(self.year, 5, 2)}
        )
        if amount is not None:
            wizard.amount = amount
            wizard.payment_difference_handling = "open"
        payments = wizard._create_payments()
        if payments.state == "draft":
            payments.action_post()
        return payments


@tagged("post_install", "-at_install")
class TestClaims(InsuranceClaimCommon):
    def test_reference_sequence_and_display_name(self):
        claim = self._claim(self._vehicle_policy())
        self.assertTrue(claim.name.startswith(f"SIN/{self.year}/"))
        self.assertEqual(claim.display_name, f"{claim.name} - INS778899")
        self.assertEqual(claim.state, "reported")
        self.assertEqual(claim.date_reported, fields.Date.context_today(claim))
        self.assertEqual(claim.insurer_id, self.insurer)

    def test_approval_entry(self):
        """Section 8.6: receivable from the insurer against the recovery
        account, due on the estimated collection date, referenced with both
        claim numbers so the bank reconciliation finds it."""
        claim = self._claim(self._vehicle_policy())
        claim.action_approve()
        self.assertEqual(claim.state, "approved")
        move = claim.move_id
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.journal_id, self.claims_journal)
        self.assertEqual(move.ref, f"{claim.name} - INS778899")
        self.assertEqual(move.insurance_claim_id, claim)
        line = self._claim_line(claim)
        self.assertEqual(claim.claim_line_id, line)
        self.assertEqual(line.debit, 450000)
        self.assertEqual(line.partner_id, self.insurer)
        self.assertEqual(line.date_maturity, date(self.year, 4, 30))
        self.assertEqual(self._amls(move, self.recovery), (0.0, 450000.0))
        self.assertEqual(claim.amount_pending, 450000)
        self.assertEqual(claim.amount_difference, 500000)

    def test_full_collection_sets_collected(self):
        claim = self._claim(self._vehicle_policy())
        claim.action_approve()
        self._collect(claim)
        self.assertEqual(claim.state, "collected")
        self.assertEqual(claim.amount_collected, 450000)
        self.assertEqual(claim.amount_pending, 0)
        self.assertEqual(claim.amount_difference, 50000)
        self.assertEqual(claim.date_collected, date(self.year, 5, 2))
        claim.action_close()
        self.assertEqual(claim.state, "closed")

    def test_partial_collection_and_close_with_difference(self):
        claim = self._claim(self._vehicle_policy())
        claim.action_approve()
        self._collect(claim, amount=400000)
        self.assertEqual(claim.state, "approved")
        self.assertEqual(claim.amount_collected, 400000)
        self.assertEqual(claim.amount_pending, 50000)
        with self.assertRaises(UserError):
            claim.action_close()
        claim.action_close_with_difference()
        self.assertEqual(claim.state, "closed")
        self.assertTrue(claim.claim_line_id.reconciled)
        difference = claim.move_ids - claim.move_id
        self.assertEqual(self._amls(difference, self.recovery), (50000.0, 0.0))
        self.assertEqual(claim.amount_collected, 450000)

    def test_no_entry_without_money(self):
        """Replacement of the item, or nothing approved: approve without entry."""
        replacement = self._claim(self._vehicle_policy(), recovery_destination="replacement")
        replacement.action_approve()
        self.assertFalse(replacement.move_id)
        replacement.action_close()
        self.assertEqual(replacement.state, "closed")
        liability = self._claim(self._vehicle_policy(policy_number="ACC-2"), claim_type="liability", amount_approved=0)
        liability.action_approve()
        self.assertFalse(liability.move_id)

    def test_missing_configuration(self):
        self.company.insurance_claim_journal_id = False
        claim = self._claim(self._vehicle_policy())
        with self.assertRaisesRegex(UserError, "claims journal"):
            claim.action_approve()

    def test_branch_accounts_take_precedence(self):
        other = self.env["account.account"].create(
            {"name": "Fleet claims", "code": "999913", "account_type": "asset_receivable", "reconcile": True}
        )
        self.branch.claim_receivable_account_id = other
        claim = self._claim(self._vehicle_policy())
        claim.action_approve()
        self.assertEqual(claim.claim_line_id.account_id, other)

    def test_cancel_approval_reverses_the_entry(self):
        claim = self._claim(self._vehicle_policy())
        claim.action_approve()
        move = claim.move_id
        claim.action_cancel_approval()
        self.assertEqual(claim.state, "analysis")
        self.assertFalse(claim.move_id)
        self.assertEqual(move.payment_state if move.is_invoice() else move.state, "posted")
        self.assertTrue(move.line_ids.filtered(lambda l: l.account_id == self.claims_receivable).reconciled)
        self.assertEqual(len(claim.move_ids), 2)

    def test_cancel_approval_blocked_after_collection(self):
        claim = self._claim(self._vehicle_policy())
        claim.action_approve()
        self._collect(claim, amount=100000)
        with self.assertRaises(UserError):
            claim.action_cancel_approval()

    def test_offset_unpaid_premium(self):
        """The insurer discounts an unpaid installment from the indemnity:
        the installment is paid by the offset and its draft payment cancelled."""
        policy = self._vehicle_policy(payment_mode_id=self.transfer_mode.id)
        installments = self._installments(policy)
        self._post_bill(policy)
        first = installments.sorted("due_date")[0]
        payment = first.payment_id
        self.assertEqual(payment.state, "draft")
        claim = self._claim(policy)
        claim.action_approve()
        wizard = self.env["insurance.claim.offset"].with_context(default_claim_id=claim.id, default_mode="insurer").create({})
        self.assertEqual(wizard.partner_id, self.insurer)
        wizard.line_ids = first.move_line_id
        self.assertEqual(wizard.amount, 100000)
        wizard.action_confirm()
        self.assertEqual(payment.state, "canceled")
        self.assertEqual(first.state, "paid")
        self.assertEqual(claim.amount_pending, 350000)
        self.assertEqual(claim.state, "approved")

    def test_offset_direct_payment_to_the_workshop(self):
        claim = self._claim(self._vehicle_policy(), recovery_destination="supplier", supplier_id=self.workshop.id)
        claim.action_approve()
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.workshop.id,
                "invoice_date": date(self.year, 3, 20),
                "invoice_line_ids": [Command.create({"name": "Repair", "quantity": 1, "price_unit": 500000, "account_id": self.expense.id, "tax_ids": []})],
            }
        )
        bill.action_post()
        wizard = self.env["insurance.claim.offset"].with_context(default_claim_id=claim.id, default_mode="supplier").create({})
        self.assertEqual(wizard.partner_id, self.workshop)
        wizard.line_ids = bill.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        self.assertEqual(wizard.amount, 450000)
        wizard.action_confirm()
        self.assertEqual(claim.state, "collected")
        self.assertEqual(bill.amount_residual, 50000)

    def test_approval_requires_accounting_rights(self):
        user = new_test_user(
            self.env, login="claim_user",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        claim = self._claim(self._vehicle_policy())
        with self.assertRaises(AccessError):
            claim.with_user(user).action_approve()
        # Without money involved, an insurance user approves on their own.
        claim.amount_approved = 0
        claim.with_user(user).action_approve()
        self.assertEqual(claim.state, "approved")

    def test_hidden_amounts_still_approve(self):
        """A user who cannot see amounts but may post entries approves the
        claim: the entry reads the amounts as superuser."""
        user = new_test_user(
            self.env, login="claim_acc",
            groups="base.group_user,insurance_management.group_insurance_user,account.group_account_invoice",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        user_group = self.env.ref("insurance_management.group_insurance_user")
        user_group._remove_group(self.env.ref("insurance_management.group_insurance_see_amounts"))
        self.assertFalse(user.has_group("insurance_management.group_insurance_see_amounts"))
        claim = self._claim(self._vehicle_policy())
        claim.with_user(user).action_approve()
        self.assertEqual(claim.claim_line_id.debit, 450000)
        with self.assertRaises(AccessError):
            claim.with_user(user).read(["amount_approved"])

    def test_coverage_warning(self):
        policy = self._vehicle_policy()
        claim = self.Claim.new({"policy_id": policy.id, "date_occurred": date(self.year - 1, 12, 31)})
        self.assertIn("not in force", claim.not_covered_warning)
        claim.date_occurred = date(self.year, 6, 1)
        self.assertFalse(claim.not_covered_warning)

    def test_only_draft_claims_can_be_deleted(self):
        policy = self._vehicle_policy()
        draft = self.Claim.create({"policy_id": policy.id, "date_occurred": date(self.year, 2, 1)})
        draft.unlink()
        claim = self._claim(policy)
        with self.assertRaises(UserError):
            claim.unlink()

    def test_effect_requires_an_object(self):
        policy = self._vehicle_policy()
        with self.assertRaises(ValidationError):
            self.Claim.create({"policy_id": policy.id, "policy_effect": "total_loss", "object_id": False})

    def test_foreign_currency_claim(self):
        usd = self.setup_other_currency("EUR", rates=[(date(self.year, 1, 1), 0.001)])
        policy = self._vehicle_policy(currency_id=usd.id)
        claim = self._claim(policy, amount_claimed=1000, amount_approved=900)
        claim.with_context(insurance_today=date(self.year, 3, 15)).action_approve()
        line = claim.claim_line_id
        self.assertEqual(line.currency_id, usd)
        self.assertEqual(line.amount_currency, 900)
        self.assertAlmostEqual(line.debit, 900000, places=2)

    # Effects on the policy -----------------------------------------------------

    def test_total_loss_of_the_last_object_cancels_the_policy(self):
        policy = self._vehicle_policy()
        self._installments(policy)
        claim = self._claim(policy, policy_effect="total_loss")
        claim.action_approve()
        self.assertTrue(claim.can_remove_object)
        action = claim.action_remove_object()
        endorsement = self.env["insurance.endorsement"].browse(action["res_id"])
        self.assertEqual(endorsement.kind, "remove_object")
        self.assertEqual(endorsement.effective_date, date(self.year, 3, 10))
        endorsement.action_confirm()
        self.assertEqual(policy.object_ids.state, "excluded")
        self.assertIn(claim.name, policy.object_ids.exclusion_reason)
        self.assertEqual(policy.state, "cancelled")
        self.assertIn(claim.name, policy.cancel_reason)
        self.assertTrue(all(i.cancelled for i in policy.installment_ids))
        self.assertEqual(len(claim.endorsement_ids), 2)
        self.assertFalse(claim.can_remove_object)

    def test_total_loss_keeps_the_policy_with_other_objects(self):
        policy = self._vehicle_policy(objects=2)
        claim = self._claim(policy, policy_effect="total_loss")
        claim.action_approve()
        endorsement = self.env["insurance.endorsement"].browse(claim.action_remove_object()["res_id"])
        endorsement.action_confirm()
        self.assertEqual(policy.state, "in_force")
        self.assertEqual(len(policy.object_ids.filtered(lambda o: o.state == "active")), 1)
        action = claim.action_insure_replacement()
        replacement = self.env["insurance.endorsement"].browse(action["res_id"])
        self.assertEqual(replacement.kind, "add_object")
        self.assertEqual(replacement.claim_id, claim)

    def test_replacement_policy_when_the_policy_ended(self):
        policy = self._vehicle_policy()
        claim = self._claim(policy, policy_effect="total_loss")
        claim.action_approve()
        self.env["insurance.endorsement"].browse(claim.action_remove_object()["res_id"]).action_confirm()
        action = claim.action_insure_replacement()
        new_policy = self.env["insurance.policy"].browse(action["res_id"])
        self.assertEqual(new_policy.state, "draft")
        self.assertEqual(new_policy.insurer_id, policy.insurer_id)
        self.assertFalse(new_policy.object_ids)
        self.assertFalse(new_policy.previous_policy_id)

    def test_reduced_sum_and_rehabilitation(self):
        policy = self._vehicle_policy()
        obj = policy.object_ids
        claim = self._claim(policy, policy_effect="reduce_sum", amount_approved=300000)
        self.assertEqual(obj.sum_available, 1000000)
        claim.action_approve()
        self.assertEqual(obj.claims_amount, 300000)
        self.assertEqual(obj.sum_available, 700000)
        self.assertTrue(claim.can_rehabilitate_sum)
        endorsement = self.env["insurance.endorsement"].browse(claim.action_rehabilitate_sum()["res_id"])
        self.assertEqual(endorsement.kind, "increase_sum")
        endorsement.action_confirm()
        self.assertTrue(claim.sum_rehabilitated)
        self.assertEqual(obj.sum_available, 1000000)

    # Claims without movement ------------------------------------------------------

    def test_stale_reminder_every_period(self):
        self.company.insurance_claim_stale_days = 10
        responsible = new_test_user(
            self.env, login="claim_resp", email="resp@example.com",
            groups="base.group_user,insurance_management.group_insurance_user",
        )
        with freeze_time(date(self.year, 3, 10)):
            claim = self._claim(self._vehicle_policy(), user_id=responsible.id)
        mails = lambda: self.env["mail.mail"].search(
            [("model", "=", "insurance.claim"), ("res_id", "=", claim.id), ("is_notification", "=", False)]
        )
        self.Claim._process_claims_batch(claim, date(self.year, 3, 19))
        self.assertFalse(mails())
        self.assertTrue(claim.with_context(insurance_today=date(self.year, 3, 20)).is_stale)
        self.assertIn(claim, self.Claim.with_context(insurance_today=date(self.year, 3, 20)).search([("is_stale", "=", True)]))
        self.Claim._process_claims_batch(claim, date(self.year, 3, 20))
        self.Claim._process_claims_batch(claim, date(self.year, 3, 21))
        self.assertEqual(len(mails()), 1)
        self.assertNotIn("450", mails().body_html or "")
        self.Claim._process_claims_batch(claim, date(self.year, 3, 30))
        self.assertEqual(len(mails()), 2)
        # A status change restarts the count.
        claim.with_context(insurance_today=date(self.year, 3, 31)).action_start_analysis()
        self.Claim._process_claims_batch(claim, date(self.year, 4, 5))
        self.assertEqual(len(mails()), 2)

    def test_claim_counters(self):
        item = self.env["insurance.insured.item"].create({"name": "Truck master"})
        policy = self._vehicle_policy(object_ids=[Command.create({"name": "Truck", "insured_item_id": item.id})])
        claim = self._claim(policy)
        self.assertEqual(policy.claim_count, 1)
        self.assertEqual(policy.object_ids.claim_count, 1)
        self.assertEqual(item.claim_count, 1)
        self.assertEqual(claim.insured_item_id, item)
        self.assertEqual(policy.action_view_claims()["domain"], [("policy_id", "=", policy.id)])
        self.assertEqual(item.action_view_claims()["domain"], [("object_id", "in", policy.object_ids.ids)])

    def test_claim_documents(self):
        claim = self._claim(self._vehicle_policy())
        wizard = self.env["insurance.policy.document.upload"].create(
            {
                "claim_id": claim.id,
                "document_type_id": self.env.ref("insurance_management.insurance_document_type_claim_photos").id,
                "file": "aGVsbG8=",
                "filename": "photo.jpg",
            }
        )
        wizard.action_upload()
        self.assertEqual(claim.document_count, 1)
        self.assertEqual(claim.attachment_ids.res_model, "insurance.claim")
