from datetime import date

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError

from .common import InsuranceCommon
from odoo.tests import tagged

TODAY = date(2026, 6, 15)


@tagged("post_install", "-at_install")
@freeze_time("2026-06-15")
class TestPolicyLifecycle(InsuranceCommon):
    def test_confirm_in_force_and_covered(self):
        policy = self._create_policy()
        self.assertEqual(policy.state, "draft")
        self.assertFalse(policy.covered_today, "Drafts are never covered")
        policy.with_user(self.insurance_user).action_confirm()
        self.assertEqual(policy.state, "in_force")
        self.assertTrue(policy.covered_today)

    def test_confirm_past_policy_is_expired(self):
        policy = self._create_policy(date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        policy.action_confirm()
        self.assertEqual(policy.state, "expired")
        self.assertFalse(policy.covered_today)

    def test_future_policy_in_force_not_covered(self):
        policy = self._create_policy(date_from=date(2026, 7, 1), date_to=date(2027, 6, 30))
        policy.action_confirm()
        self.assertEqual(policy.state, "in_force")
        self.assertFalse(policy.covered_today)

    def test_end_date_is_inclusive(self):
        """On date_to the policy is still in force and covered; it expires
        the day after."""
        policy = self._create_policy(date_from=date(2025, 6, 16), date_to=TODAY)
        policy.action_confirm()
        self.assertEqual(policy.state, "expiring", "On its end date it is still Expiring")
        self.assertTrue(policy.covered_today)
        self.assertFalse(policy._apply_lifecycle_state(TODAY))
        tomorrow = date(2026, 6, 16)
        self.assertEqual(policy._apply_lifecycle_state(tomorrow), policy)
        self.assertEqual(policy.state, "expired")
        self.assertFalse(policy.with_context(insurance_today=tomorrow).covered_today)
        self.assertTrue(policy.covered_today, "Today (date_to) it is still covered")

    def test_covered_today_search(self):
        covered = self._create_policy(policy_number="A")
        covered.action_confirm()
        future = self._create_policy(policy_number="B", date_from=date(2026, 7, 1), date_to=date(2027, 6, 30))
        future.action_confirm()
        draft = self._create_policy(policy_number="C")
        expired = self._create_policy(policy_number="D", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        expired.action_confirm()
        cancelled = self._create_policy(policy_number="E")
        cancelled.action_confirm()
        cancelled.with_context(insurance_lifecycle_write=True).write({"state": "cancelled"})
        self.assertFalse(cancelled.covered_today)
        policies = covered | future | draft | expired | cancelled
        Policy = self.env["insurance.policy"]
        self.assertEqual(Policy.search([("id", "in", policies.ids), ("covered_today", "=", True)]), covered)
        self.assertEqual(
            Policy.search([("id", "in", policies.ids), ("covered_today", "=", False)]),
            future | draft | expired | cancelled,
        )

    def test_state_only_changes_through_actions(self):
        policy = self._create_policy()
        with self.assertRaises(UserError):
            policy.write({"state": "in_force"})
        with self.assertRaises(UserError):
            self.env["insurance.policy"].create(self._policy_vals(state="in_force"))

    def test_locked_states_are_read_only(self):
        policy = self._create_policy(date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        policy.action_confirm()
        self.assertTrue(policy.is_locked)
        with self.assertRaises(UserError):
            policy.write({"premium_total": 5000.0})
        with self.assertRaises(UserError):
            policy.with_user(self.insurance_manager).write({"policy_number": "NEW"})
        # The chatter keeps working on a locked policy.
        policy.message_post(body="Still allowed")

    def test_confirmed_policy_contract_only_by_endorsement(self):
        """Fase 2: contract data of a confirmed policy only change through an
        endorsement; the rest stays editable and changes are tracked."""
        policy = self._create_policy()
        policy.action_confirm()
        self.env.cr.flush()
        for values in ({"premium_total": 1500.0}, {"date_to": date(2026, 11, 30)}, {"insurer_id": self.insurer_2.id}):
            with self.subTest(values=values), self.assertRaises(UserError):
                policy.with_user(self.insurance_user).write(values)
        # Administrative fields stay editable.
        policy.with_user(self.insurance_user).write({"user_id": self.insurance_manager.id, "note": "<p>ok</p>"})
        # An endorsement can change them, and the change is tracked.
        policy.with_context(insurance_endorsement_write=True).write({"premium_total": 1500.0})
        self.env.flush_all()
        self.env.cr.flush()
        policy.invalidate_recordset(["message_ids"])
        tracked = policy.message_ids.tracking_value_ids.filtered(lambda t: t.field_id.name == "premium_total")
        self.assertTrue(tracked)
        self.assertEqual((tracked[0].old_value_float, tracked[0].new_value_float), (1210.0, 1500.0))

    def test_moving_end_date_updates_state(self):
        policy = self._create_policy()
        policy.action_confirm()
        policy.with_context(insurance_endorsement_write=True).write(
            {"date_from": date(2025, 6, 1), "date_to": date(2026, 5, 31)}
        )
        self.assertEqual(policy.state, "expired")

    def test_reset_to_draft_only_administrator(self):
        policy = self._create_policy()
        policy.action_confirm()
        with self.assertRaises(AccessError):
            policy.with_user(self.insurance_user).action_reset_to_draft()
        policy.with_user(self.insurance_manager).action_reset_to_draft()
        self.assertEqual(policy.state, "draft")
        with self.assertRaises(UserError):
            policy.with_user(self.insurance_manager).action_reset_to_draft()
        expired = self._create_policy(
            policy_number="EXP", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31)
        )
        expired.action_confirm()
        expired.with_user(self.insurance_manager).action_reset_to_draft()
        self.assertEqual(expired.state, "draft")
        expired.action_confirm()
        expired.with_context(insurance_lifecycle_write=True).write({"state": "cancelled"})
        with self.assertRaises(UserError):
            expired.with_user(self.insurance_manager).action_reset_to_draft()

    def test_only_drafts_can_be_deleted(self):
        draft = self._create_policy(policy_number="DRAFT")
        draft.with_user(self.insurance_user).unlink()
        policy = self._create_policy()
        policy.action_confirm()
        with self.assertRaises(UserError):
            policy.with_user(self.insurance_manager).unlink()

    def test_kanban_shows_all_states(self):
        self.assertTrue(self.env["insurance.policy"]._fields["state"].group_expand)
        result = (
            self.env["insurance.policy"]
            .with_context(read_group_expand=True)
            .web_read_group([("id", "=", 0)], groupby=["state"], aggregates=["__count"])
        )
        self.assertEqual(
            [group["state"] for group in result["groups"]],
            ["draft", "in_force", "expiring", "expired", "renewed", "not_renewed", "cancelled"],
        )
