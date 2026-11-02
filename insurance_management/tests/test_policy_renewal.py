from datetime import date

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import InsuranceCommon

LIFECYCLE = {"insurance_lifecycle_write": True}


@tagged("post_install", "-at_install")
@freeze_time("2026-12-10")
class TestPolicyRenewal(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.producer.email = "producer@example.com"
        cls.insurer.email = "insurer@example.com"
        cls.item = cls.env["insurance.insured.item"].create({"name": "Main warehouse"})
        cls.tag = cls.env["insurance.policy.tag"].create({"name": "Fleet"})

    def _expiring_policy(self, **values):
        """A policy in force 01/01/2026 - 31/12/2026 moved to Expiring (the
        alert process that does it arrives in a later stage)."""
        vals = {
            "coverage": "<p>All risks</p>",
            "tag_ids": [(6, 0, self.tag.ids)],
            "deductible_type": "amount",
            "deductible_amount": 500,
            "object_ids": [
                (0, 0, {"name": "Truck", "license_plate": "AB123CD", "sum_insured": 123456, "coverage": "All risks", "insured_item_id": self.item.id}),
                (0, 0, {"name": "Van", "license_plate": "AC456EF", "sum_insured": 65432}),
            ],
        }
        vals.update(values)
        policy = self._create_policy(**vals)
        policy.action_confirm()
        policy.with_context(**LIFECYCLE).write({"state": "expiring"})
        return policy

    def test_renew_creates_linked_draft(self):
        policy = self._expiring_policy()
        policy.object_ids.filtered(lambda o: o.name == "Van")._exclude(date(2026, 6, 1), "Sold")
        action = policy.with_user(self.insurance_user).action_renew()
        renewal = self.env["insurance.policy"].browse(action["res_id"])
        self.assertEqual(renewal.state, "draft")
        self.assertFalse(renewal.policy_number, "The insurer issues the new number")
        self.assertEqual((renewal.date_from, renewal.date_to), (date(2027, 1, 1), date(2027, 12, 31)))
        self.assertEqual(renewal.duration_months, policy.duration_months)
        self.assertEqual(
            (renewal.branch_id, renewal.insurer_id, renewal.producer_id, renewal.user_id),
            (policy.branch_id, policy.insurer_id, policy.producer_id, policy.user_id),
        )
        self.assertEqual(renewal.coverage, policy.coverage)
        self.assertEqual(renewal.tag_ids, self.tag)
        self.assertEqual(renewal.deductible_amount, 500)
        self.assertEqual(renewal.object_ids.mapped("name"), ["Truck"], "Only active objects are copied")
        self.assertEqual(renewal.object_ids.insured_item_id, self.item, "The master link is kept")
        self.assertEqual(renewal.object_ids.date_start, date(2027, 1, 1))
        self.assertEqual(renewal.sum_insured_total, 123456)
        # Two-way link and history.
        self.assertEqual(policy.renewed_by_id, renewal)
        self.assertEqual(renewal.previous_policy_id, policy)
        self.assertEqual(policy.renewal_type, "renew")
        self.assertEqual(policy.renewal_count, 2)
        self.assertEqual(
            self.env["insurance.policy"].search(renewal.action_view_renewals()["domain"]),
            policy | renewal,
        )
        # Without a number the renewal cannot be confirmed.
        with self.assertRaises(UserError):
            renewal.action_confirm()

    def test_original_stays_covered_until_end_date(self):
        policy = self._expiring_policy()
        policy.action_renew()
        self.assertEqual(policy.state, "expiring")
        self.assertTrue(policy.covered_today)
        self.assertFalse(policy._apply_lifecycle_state(date(2026, 12, 31)))
        self.assertTrue(policy.with_context(insurance_today=date(2026, 12, 31)).covered_today)
        policy._apply_lifecycle_state(date(2027, 1, 1))
        self.assertEqual(policy.state, "renewed")

    def test_late_renewal_of_expired_policy(self):
        policy = self._create_policy(date_from=date(2025, 12, 1), date_to=date(2026, 11, 30))
        policy.action_confirm()
        self.assertEqual(policy.state, "expired")
        renewal = self.env["insurance.policy"].browse(policy.action_renew()["res_id"])
        self.assertEqual(policy.state, "renewed", "A late renewal is applied right away")
        self.assertEqual(renewal.date_from, date(2026, 12, 1))
        # Deleting the renewal draft puts the policy back to Expired.
        renewal.unlink()
        self.assertFalse(policy.renewed_by_id)
        self.assertEqual(policy.state, "expired")
        self.assertIn("renewal draft", policy.message_ids[0].body)

    def test_renew_only_when_expiring_or_expired_and_once(self):
        draft = self._create_policy(policy_number="D")
        with self.assertRaises(UserError):
            draft.action_renew()
        in_force = self._create_policy(policy_number="F", date_from=date(2026, 7, 1), date_to=date(2027, 6, 30))
        in_force.action_confirm()
        with self.assertRaises(UserError):
            in_force.action_renew()
        policy = self._expiring_policy()
        policy.action_renew()
        with self.assertRaises(UserError):
            policy.action_renew()

    def test_keep_number_on_renewal(self):
        policy = self._expiring_policy(keep_number_on_renewal=True)
        renewal = self.env["insurance.policy"].browse(policy.action_renew()["res_id"])
        self.assertEqual(renewal.policy_number, policy.policy_number)
        self.assertTrue(renewal.keep_number_on_renewal)
        renewal.action_confirm()
        self.assertEqual(renewal.state, "in_force")

    def test_same_duration_for_partial_months(self):
        policy = self._create_policy(date_from=date(2026, 6, 15), date_to=date(2026, 12, 14))
        policy.action_confirm()
        policy.with_context(**LIFECYCLE).write({"state": "expiring"})
        renewal = self.env["insurance.policy"].browse(policy.action_renew()["res_id"])
        self.assertEqual((renewal.date_from, renewal.date_to), (date(2026, 12, 15), date(2027, 6, 14)))

    def test_non_renewal_with_instruction_to_producer(self):
        policy = self._expiring_policy(user_id=self.insurance_manager.id)
        action = policy.with_user(self.insurance_user).action_open_non_renewal_wizard()
        wizard_form = Form(
            self.env[action["res_model"]].with_user(self.insurance_user).with_context(action["context"])
        )
        wizard_form.reason = "Vehicles sold"
        wizard_form.cc_insurer = True
        wizard = wizard_form.save()
        wizard.action_confirm()
        self.assertEqual(policy.renewal_type, "no_renew")
        self.assertEqual(policy.non_renewal_reason, "Vehicles sold")
        self.assertEqual(policy.non_renewal_date, date(2026, 12, 10))
        self.assertTrue(policy.non_renewal_sent_date)
        message = policy.message_ids.filtered(lambda m: m.message_type == "comment")[:1]
        self.assertIn(policy.policy_number, message.subject)
        spanish = (self.producer.lang or "").startswith("es")
        self.assertIn("no renueve" if spanish else "do not renew", message.body)
        self.assertIn("Truck", message.body)
        for amount in ("123456", "123.456", "123,456"):
            self.assertNotIn(amount, message.body, "No amounts in the email")
        self.assertIn(self.producer, message.partner_ids)
        self.assertIn(self.insurer, message.partner_ids)
        self.assertIn(policy.user_id.partner_id, message.partner_ids)
        self.assertIn(policy.company_id.name, message.body)
        # Still covered and expiring until the end date, then Not renewed.
        self.assertEqual(policy.state, "expiring")
        policy._apply_lifecycle_state(date(2027, 1, 1))
        self.assertEqual(policy.state, "not_renewed")

    def test_non_renewal_without_sending(self):
        policy = self._expiring_policy()
        wizard = self.env["insurance.policy.non.renewal"].create(
            {"policy_id": policy.id, "reason": "Too expensive", "send_instruction": False}
        )
        wizard.action_confirm()
        self.assertEqual(policy.renewal_type, "no_renew")
        self.assertFalse(policy.non_renewal_sent_date)

    def test_non_renewal_requires_reason_and_producer_email(self):
        policy = self._expiring_policy()
        wizard_form = Form(self.env["insurance.policy.non.renewal"].with_context(default_policy_id=policy.id))
        with self.assertRaises(AssertionError, msg="The reason is required"):
            wizard_form.save()
        self.producer.email = False
        wizard = self.env["insurance.policy.non.renewal"].create(
            {"policy_id": policy.id, "reason": "No email"}
        )
        with self.assertRaises(UserError):
            wizard.action_confirm()

    def test_non_renewal_only_before_expiry(self):
        expired = self._create_policy(date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        expired.action_confirm()
        with self.assertRaises(UserError):
            expired.action_open_non_renewal_wizard()
        draft = self._create_policy(policy_number="DRAFT")
        with self.assertRaises(UserError):
            draft._mark_non_renewal("Draft")

    def test_renew_after_non_renewal_switches_decision(self):
        policy = self._expiring_policy()
        policy._mark_non_renewal("Changed our mind later")
        policy._send_non_renewal_instruction()
        renewal = self.env["insurance.policy"].browse(policy.action_renew()["res_id"])
        self.assertEqual(policy.renewal_type, "renew")
        self.assertTrue(
            any("already sent to the producer" in (m.body or "") for m in policy.message_ids),
            "The chatter warns that the instruction had been sent",
        )
        policy._apply_lifecycle_state(date(2027, 1, 1))
        self.assertEqual(policy.state, "renewed")
        self.assertTrue(renewal)

    def test_request_renewal_composer(self):
        policy = self._create_policy()
        policy.action_confirm()
        action = policy.with_user(self.insurance_user).action_request_renewal()
        self.assertEqual(action["res_model"], "mail.compose.message")
        composer = (
            self.env["mail.compose.message"]
            .with_user(self.insurance_user)
            .with_context(action["context"])
            .create({})
        )
        spanish = (self.producer.lang or "").startswith("es")
        self.assertIn("Solicitud de renovación" if spanish else "Renewal request", composer.subject)
        composer._action_send_mail()
        self.assertTrue(policy.renewal_request_sent_date)
        message = policy.message_ids.filtered(lambda m: m.message_type == "comment")[:1]
        self.assertIn("propuesta de renovación" if spanish else "renewal proposal", message.body)
        self.assertIn(self.producer, message.partner_ids)

    def test_producer_email_in_producer_language(self):
        self.env["res.lang"]._activate_lang("es_AR")
        self.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        self.producer.lang = "es_AR"
        policy = self._expiring_policy()
        policy._mark_non_renewal("Idioma")
        policy._send_non_renewal_instruction()
        message = policy.message_ids.filtered(lambda m: m.message_type == "comment")[:1]
        self.assertIn("Instrucción de no renovación", message.subject)
        self.assertIn("no renueve", message.body)
