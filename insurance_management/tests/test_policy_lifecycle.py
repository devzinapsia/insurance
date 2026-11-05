from datetime import date

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user

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

    def test_confirm_warns_when_premium_is_zero(self):
        policy = self._create_policy(premium=0, premium_total=0)
        button = policy.with_context(insurance_check_amounts=True)
        action = button.action_confirm()
        self.assertEqual(action["res_model"], "insurance.policy.confirm.warning")
        self.assertEqual(policy.state, "draft", "Nothing confirmed before the user decides")
        # As in the web client: the button context reaches the dialog.
        wizard = self.env[action["res_model"]].with_context(insurance_check_amounts=True, **action["context"]).create({})
        self.assertEqual(wizard.zero_policy_ids, policy)
        wizard.action_confirm()
        self.assertEqual(policy.state, "in_force", "Confirm anyway")
        self.assertTrue(any("at zero" in (body or "") for body in policy.message_ids.mapped("body")), "Logged in the chatter")
        # Only the total premium at zero also warns.
        other = self._create_policy(policy_number="POL-ZERO", premium=1000, premium_total=0)
        self.assertIsInstance(other.with_context(insurance_check_amounts=True).action_confirm(), dict)
        # With both amounts, the button confirms directly.
        normal = self._create_policy(policy_number="POL-OK")
        self.assertIs(normal.with_context(insurance_check_amounts=True).action_confirm(), True)
        self.assertEqual(normal.state, "in_force")

    def test_zero_premium_never_blocks_code_or_users_without_amounts(self):
        imported = self._create_policy(premium=0, premium_total=0)
        self.assertIs(imported.action_confirm(), True, "Code callers (import) are never asked")
        self.assertEqual(imported.state, "in_force")
        self.env.ref("insurance_management.group_insurance_user").sudo()._remove_group(
            self.env.ref("insurance_management.group_insurance_see_amounts").sudo()
        )
        hidden = new_test_user(self.env, login="confirm_no_amounts", groups="base.group_user,insurance_management.group_insurance_user")
        policy = self._create_policy(policy_number="POL-HIDDEN", premium=0, premium_total=0)
        self.assertIs(policy.with_user(hidden).with_context(insurance_check_amounts=True).action_confirm(), True)

    def test_confirm_past_policy_is_expired(self):
        policy = self._create_policy(date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        policy.action_confirm()
        self.assertEqual(policy.state, "expired")
        self.assertFalse(policy.covered_today)

    def test_future_policy_not_started(self):
        """Confirmed before its start date: Not started (not in force, not
        covered, no expiry notice); the daily process starts it on its start
        date."""
        policy = self._create_policy(date_from=date(2026, 6, 17), date_to=date(2026, 7, 16))
        policy.action_confirm()
        self.assertEqual(policy.state, "not_started", "Within the 30 days alert, but it has not started")
        self.assertFalse(policy.covered_today)
        self.assertNotIn(policy, self.env["insurance.policy"].search([("state", "in", ("in_force", "expiring"))]))
        Policy = self.env["insurance.policy"]
        Policy._process_expiry_batch(policy, TODAY)
        self.assertEqual(policy.state, "not_started")
        self.assertFalse(policy.alert_ids, "No expiry notice before it starts")
        Policy._process_expiry_batch(policy, date(2026, 6, 17))
        self.assertEqual(policy.state, "expiring", "Started, already within the 30 days alert")
        self.assertTrue(policy.alert_ids, "The pending notice is sent the day it starts")

    def test_not_started_policy_is_locked_but_endorsable(self):
        policy = self._create_policy(date_from=date(2026, 7, 1), date_to=date(2027, 6, 30))
        policy.action_confirm()
        self.assertEqual(policy.state, "not_started")
        with self.assertRaises(UserError):
            policy.premium_total = 2000
        action = policy.action_new_endorsement()
        self.assertEqual(action["context"]["default_effective_date"], "2026-07-01", "Proposed from its start date")
        self._endorse(policy, "data_change", description="Producer contact changed", effective_date=date(2026, 7, 1))
        self.assertEqual(policy.endorsement_count, 1)
        # Moving the start date to today (by endorsement) starts it.
        policy.with_context(insurance_endorsement_write=True, insurance_skip_duration_check=True).date_from = TODAY
        self.assertEqual(policy.state, "in_force")

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
            ["draft", "not_started", "in_force", "expiring", "expired", "renewed", "not_renewed", "cancelled"],
        )
