import base64
from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .test_claims import InsuranceClaimCommon


@tagged("post_install", "-at_install")
class TestSureties(InsuranceClaimCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.surety_branch = cls.env.ref("insurance_management.insurance_branch_surety")
        cls.beneficiary = cls.env["res.partner"].create(
            {"name": "City council", "is_company": True, "email": "council@example.com"}
        )
        cls.producer.email = "producer@example.com"
        cls.release_type = cls.env.ref("insurance_management.insurance_document_type_surety_release")

    def _surety(self, **values):
        vals = {
            "branch_id": self.surety_branch.id,
            "policy_number": "CAU-1",
            "renewal_type": "until_release",
            "surety_beneficiary_id": self.beneficiary.id,
            "surety_type": "performance",
            "surety_obligation": "Tender 12/2026",
            "surety_amount": 5000000,
            "surety_obligation_end": date(self.year, 12, 31),
            "object_ids": [Command.create({"name": "Performance of contract 12/2026"})],
        }
        vals.update(values)
        return self._policy(**vals)

    def _attach_release(self, policy):
        return self.env["ir.attachment"].create(
            {
                "name": "release.pdf",
                "datas": base64.b64encode(b"release"),
                "res_model": "insurance.policy",
                "res_id": policy.id,
                "insurance_document_type_id": self.release_type.id,
            }
        )

    def test_surety_flag_and_until_release_only_for_sureties(self):
        policy = self._surety()
        self.assertTrue(policy.is_surety)
        self.assertEqual(policy.surety_state, "issued")
        with self.assertRaises(ValidationError):
            self._policy(policy_number="ACC-9", renewal_type="until_release")

    def test_guarantee_workflow_requires_the_release_certificate(self):
        policy = self._surety()
        policy.action_surety_deliver()
        self.assertEqual(policy.surety_state, "delivered")
        with self.assertRaisesRegex(UserError, "release certificate"):
            policy.action_surety_release()
        self._attach_release(policy)
        action = policy.action_surety_release()
        self.assertEqual(policy.surety_state, "released")
        self.assertTrue(policy.surety_release_date)
        self.assertEqual(action["res_model"], "mail.compose.message")
        self.assertEqual(
            action["context"]["default_template_id"],
            self.env.ref("insurance_management.mail_template_surety_released").id,
        )
        policy.action_surety_return()
        self.assertEqual(policy.surety_state, "returned")

    def test_until_release_does_not_expire_with_the_guarantee_open(self):
        policy = self._surety(date_from=date(self.year - 1, 1, 1), date_to=date(self.year - 1, 12, 31))
        today = date(self.year, 2, 1)
        Policy = self.env["insurance.policy"].with_context(insurance_today=today)
        policy = Policy.browse(policy.id)
        policy._apply_lifecycle_state(today)
        self.assertEqual(policy.state, "expiring")
        self.assertTrue(policy.covered_today)
        self.assertIn(policy, Policy.search([("covered_today", "=", True)]))
        # Once a day: one activity to renew or release, never duplicated.
        Policy._process_expiry_batch(policy, today)
        Policy._process_expiry_batch(policy, today)
        activity_type = self.env.ref("insurance_management.mail_activity_type_surety_release")
        unreleased = policy.alert_ids.filtered(lambda a: a.alert_type == "surety_unreleased")
        self.assertEqual(len(unreleased), 1)
        self.assertTrue(policy.activity_ids.filtered(lambda a: a.activity_type_id == activity_type))
        # Released: the policy ends as not renewed.
        self._attach_release(policy)
        policy.with_context(insurance_today=today).action_surety_release()
        self.assertEqual(policy.state, "not_renewed")
        self.assertFalse(policy.activity_ids.filtered(lambda a: a.activity_type_id == activity_type))

    def test_release_request_manual_creates_an_activity_once(self):
        policy = self._surety(surety_obligation_end=date(self.year, 7, 15))
        Policy = self.env["insurance.policy"]
        Policy._process_expiry_batch(policy, date(self.year, 6, 1))
        self.assertFalse(policy.alert_ids.filtered(lambda a: a.alert_type == "surety_release_request"))
        Policy._process_expiry_batch(policy, date(self.year, 6, 20))
        Policy._process_expiry_batch(policy, date(self.year, 6, 21))
        requests = policy.alert_ids.filtered(lambda a: a.alert_type == "surety_release_request")
        self.assertEqual(len(requests), 1)
        activity_type = self.env.ref("insurance_management.mail_activity_type_surety_release")
        self.assertEqual(len(policy.activity_ids.filtered(lambda a: a.activity_type_id == activity_type)), 1)
        self.assertFalse(policy.surety_release_requested_on)

    def test_release_request_automatic_emails_the_beneficiary(self):
        self.company.insurance_surety_release_send_mode = "automatic"
        policy = self._surety(surety_obligation_end=date(self.year, 7, 15))
        self.env["insurance.policy"]._process_expiry_batch(policy, date(self.year, 6, 20))
        message = policy.message_ids.filtered(lambda m: m.message_type == "comment")[:1]
        self.assertTrue(message)
        self.assertIn(self.beneficiary, message.partner_ids)
        self.assertIn("Tender 12/2026", message.body)
        self.assertTrue(policy.surety_release_requested_on)
        # Without a beneficiary email, the producer is asked instead.
        self.beneficiary.email = False
        self.assertEqual(policy._get_surety_release_recipient(), self.producer)

    def test_renewal_copies_the_guarantee_and_only_the_last_policy_counts(self):
        policy = self._surety(date_from=date(self.year - 1, 1, 1), date_to=date(self.year - 1, 12, 31))
        policy.action_surety_deliver()
        policy = policy.with_context(insurance_today=date(self.year, 1, 5))
        policy._apply_lifecycle_state(date(self.year, 1, 5))
        renewal = self.env["insurance.policy"].browse(policy.action_renew()["res_id"])
        self.assertEqual(renewal.surety_beneficiary_id, self.beneficiary)
        self.assertEqual(renewal.surety_amount, 5000000)
        self.assertEqual(renewal.surety_state, "delivered")
        self.assertEqual(renewal.renewal_type, "until_release")
        self.assertEqual(policy.state, "renewed")
        self.assertFalse(policy._surety_is_open())
        action = self.env.ref("insurance_management.insurance_policy_surety_action")
        listed = self.env["insurance.policy"].search(eval(action.domain))
        self.assertNotIn(policy, listed)
        with self.assertRaises(UserError):
            policy.action_surety_release()

    def test_surety_execution(self):
        """The accounting is inverted: a loss against the debt with the
        insurer, the guarantee is executed and the policy ends."""
        policy = self._surety()
        self._installments(policy)
        claim = self.Claim.create(
            {
                "policy_id": policy.id,
                "claim_type": "surety_execution",
                "date_occurred": date(self.year, 5, 10),
                "amount_claimed": 2000000,
                "amount_approved": 2000000,
            }
        )
        self.assertEqual(claim.policy_effect, "surety_execution")
        claim.action_report()
        claim.action_approve()
        payable = claim.claim_line_id
        self.assertEqual(payable.account_id, self.insurer.property_account_payable_id)
        self.assertEqual(payable.credit, 2000000)
        self.assertEqual(self._amls(claim.move_id, self.surety_loss), (2000000.0, 0.0))
        self.assertEqual(policy.surety_state, "executed")
        self.assertEqual(policy.state, "cancelled")
        self.assertIn(claim.name, policy.cancel_reason)
        self.assertTrue(all(i.cancelled for i in policy.installment_ids))
        with self.assertRaises(UserError):
            claim.action_cancel_approval()
        claim.action_close()
        self.assertEqual(claim.state, "closed")

    def test_only_sureties_can_be_executed(self):
        policy = self._policy(object_ids=[Command.create({"name": "Truck"})])
        with self.assertRaises(ValidationError):
            self.Claim.create({"policy_id": policy.id, "claim_type": "surety_execution", "policy_effect": "surety_execution"})
