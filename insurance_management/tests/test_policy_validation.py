from datetime import date

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged
from odoo.tools import mute_logger

from .common import InsuranceCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-06-15")
class TestPolicyValidation(InsuranceCommon):
    def test_end_date_after_start_date(self):
        for date_to in (date(2025, 12, 31), date(2026, 1, 1)):
            with self.subTest(date_to=date_to), self.assertRaises(ValidationError):
                self._create_policy(date_to=date_to)

    def test_duration_computation(self):
        cases = [
            (date(2026, 1, 1), date(2026, 12, 31), 12, 0),
            (date(2026, 3, 15), date(2026, 9, 14), 6, 0),
            (date(2026, 1, 1), date(2026, 1, 20), 0, 20),
            (date(2026, 1, 31), date(2026, 3, 2), 1, 3),
        ]
        for date_from, date_to, months, days in cases:
            with self.subTest(date_from=date_from, date_to=date_to):
                policy = self._create_policy(policy_number=False, date_from=date_from, date_to=date_to)
                self.assertEqual((policy.duration_months, policy.duration_days), (months, days))

    def test_confirm_requires_number_and_validity(self):
        for missing in ("policy_number", "date_from", "date_to"):
            with self.subTest(missing=missing):
                policy = self._create_policy(**{missing: False})
                with self.assertRaises(UserError):
                    policy.action_confirm()
                self.assertEqual(policy.state, "draft")

    def test_duration_block_mode(self):
        too_long = self._create_policy(date_from=date(2026, 1, 1), date_to=date(2027, 6, 30))
        self.assertTrue(too_long.duration_warning)
        with self.assertRaises(ValidationError):
            too_long.action_confirm()
        too_short = self._create_policy(
            policy_number="POL-002", date_from=date(2026, 6, 1), date_to=date(2026, 6, 20)
        )
        with self.assertRaises(ValidationError):
            too_short.action_confirm()
        exact_max = self._create_policy(
            policy_number="POL-003", date_from=date(2026, 3, 15), date_to=date(2027, 3, 14)
        )
        self.assertFalse(exact_max.duration_warning)
        exact_max.action_confirm()
        self.assertEqual(exact_max.state, "in_force")
        # A confirmed policy cannot be stretched beyond the maximum either.
        with self.assertRaises(ValidationError):
            exact_max.with_context(insurance_endorsement_write=True).write({"date_to": date(2027, 4, 30)})

    def test_duration_warning_mode(self):
        self.company.insurance_duration_check = "warning"
        policy = self._create_policy(date_from=date(2026, 1, 1), date_to=date(2027, 6, 30))
        policy.action_confirm()
        self.assertEqual(policy.state, "in_force")
        self.assertTrue(
            any("duration warning" in (msg.body or "") for msg in policy.message_ids),
            "Confirming out of range in warning mode leaves a chatter note",
        )

    def test_duration_onchange_warning(self):
        with Form(self.env["insurance.policy"]) as form:
            form.branch_id = self.branch
            form.insurer_id = self.insurer
            form.producer_id = self.producer
            form.date_from = date(2026, 1, 1)
            form.date_to = date(2027, 6, 30)
            self.assertTrue(form.duration_warning)
            form.date_to = date(2026, 12, 31)
            self.assertFalse(form.duration_warning)

    def test_number_unique_per_insurer_company_and_start(self):
        self._create_policy()
        # Same number on a renewal (other start date), another insurer, or
        # drafts without number are all allowed.
        self._create_policy(date_from=date(2027, 1, 1), date_to=date(2027, 12, 31))
        self._create_policy(insurer_id=self.insurer_2.id)
        self._create_policy(policy_number=False)
        self._create_policy(policy_number=False)
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._create_policy()
                self.env.flush_all()

    def test_reference_sequence_per_company(self):
        policy = self._create_policy()
        self.assertTrue(policy.name.startswith("SEG/2026/"), policy.name)
        company_b = self.env["res.company"].create({"name": "Insurance company B"})
        policy_b = self.env["insurance.policy"].with_company(company_b).create(
            self._policy_vals(company_id=company_b.id, branch_id=self.branch_fire.id)
        )
        self.assertEqual(policy_b.name, "SEG/2026/0001")
        self.assertNotEqual(
            self.env["insurance.policy"]._get_policy_sequence(company_b),
            self.env["insurance.policy"]._get_policy_sequence(self.company),
        )
        self.assertIn(policy.policy_number, policy.display_name)

    def test_company_duration_limits(self):
        with self.assertRaises(ValidationError):
            self.company.insurance_min_duration_months = 0
        with self.assertRaises(ValidationError):
            self.company.write(
                {"insurance_min_duration_months": 6, "insurance_max_duration_months": 3}
            )
