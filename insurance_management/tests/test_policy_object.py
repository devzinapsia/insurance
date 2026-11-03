from datetime import date

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import InsuranceCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-06-15")
class TestPolicyObject(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.item = cls.env["insurance.insured.item"].create(
            {"name": "Main warehouse", "item_type": "real_estate", "reference_value": 900000}
        )

    def _policy_with_objects(self):
        policy = self._create_policy(
            object_ids=[
                (0, 0, {"name": "Truck AB123CD", "license_plate": "AB123CD", "sum_insured": 100000}),
                (0, 0, {"name": "Van AC456EF", "license_plate": "AC456EF", "sum_insured": 50000}),
            ]
        )
        return policy

    def test_sum_insured_total_counts_active_objects(self):
        policy = self._policy_with_objects()
        self.assertEqual(policy.sum_insured_total, 150000)
        self.assertEqual(policy.object_count, 2)
        self.assertEqual(policy.object_ids.mapped("date_start"), [date(2026, 1, 1)] * 2)

    def test_remove_object_keeps_history(self):
        policy = self._policy_with_objects()
        policy.action_confirm()
        van = policy.object_ids.filtered(lambda o: o.license_plate == "AC456EF")
        endorsement = self._endorse(
            policy, "remove_object", user=self.insurance_user, effective_date=date(2026, 6, 10),
            lines=[{"operation": "remove", "object_id": van.id, "reason": "Vehicle sold"}],
        )
        self.assertEqual(van.state, "excluded")
        self.assertEqual(van.date_end, date(2026, 6, 10))
        self.assertEqual(van.exclusion_reason, "Vehicle sold")
        self.assertEqual(van.endorsement_out_id, endorsement)
        self.assertIn(van, policy.object_ids, "Removed objects stay as history")
        self.assertEqual(policy.sum_insured_total, 100000)
        self.assertEqual(policy.object_count, 1)
        with self.assertRaises(UserError):
            van.with_context(insurance_endorsement_write=True)._exclude(date(2026, 6, 11), "Twice")

    def test_removal_date_not_before_added(self):
        policy = self._policy_with_objects()
        policy.action_confirm()
        added = self._endorse(
            policy, "add_object", effective_date=date(2026, 3, 1), lines=[{"operation": "add", "name": "Car", "sum_insured": 10}]
        )
        car = policy.object_ids.filtered(lambda o: o.endorsement_in_id == added)
        with self.assertRaises(UserError):
            self._endorse(
                policy, "remove_object", effective_date=date(2026, 2, 1),
                lines=[{"operation": "remove", "object_id": car.id, "reason": "Too early"}],
            )

    def test_objects_of_confirmed_policy_only_by_endorsement(self):
        policy = self._policy_with_objects()
        policy.action_confirm()
        with self.assertRaises(UserError):
            policy.object_ids[0].with_user(self.insurance_user).write({"sum_insured": 1})
        with self.assertRaises(UserError):
            self.env["insurance.policy.object"].with_user(self.insurance_user).create({"policy_id": policy.id, "name": "New"})
        with self.assertRaises(UserError):
            policy.object_ids[0].with_user(self.insurance_user)._exclude(date(2026, 6, 1), "No endorsement")

    def test_delete_object_only_on_draft(self):
        policy = self._policy_with_objects()
        policy.object_ids[0].with_user(self.insurance_user).unlink()
        self.assertEqual(policy.object_count, 1)
        policy.action_confirm()
        with self.assertRaises(UserError):
            policy.object_ids.unlink()

    def test_changes_on_confirmed_policy_logged_with_old_and_new(self):
        policy = self._policy_with_objects()
        policy.action_confirm()
        truck = policy.object_ids.filtered(lambda o: o.license_plate == "AB123CD")
        self._endorse(
            policy, "increase_sum", user=self.insurance_user, effective_date=date(2026, 6, 1),
            lines=[{"operation": "change", "object_id": truck.id, "sum_insured": 120000, "coverage": "All risks"}],
        )
        self.assertEqual(truck.sum_insured, 120000)
        message = policy.message_ids.filtered(lambda m: "Truck AB123CD" in (m.body or ""))[:1]
        trackings = {t.field_id.name: t for t in message.tracking_value_ids}
        self.assertEqual(trackings["sum_insured"].old_value_float, 100000)
        self.assertEqual(trackings["sum_insured"].new_value_float, 120000)
        self.assertEqual(trackings["coverage"].new_value_char, "All risks")
        self.assertEqual(policy.sum_insured_total, 170000)
        # Adding an object is logged too, dated with the endorsement.
        endorsement = self._endorse(
            policy, "add_object", effective_date=date(2026, 6, 15),
            lines=[{"operation": "add", "name": "Car AD789GH", "sum_insured": 30000, "insured_item_id": self.item.id}],
        )
        new_object = policy.object_ids.filtered(lambda o: o.name == "Car AD789GH")
        self.assertEqual(new_object.date_start, date(2026, 6, 15))
        self.assertEqual(new_object.endorsement_in_id, endorsement)
        self.assertTrue(any("Car AD789GH" in (m.body or "") for m in policy.message_ids))

    def test_drafts_do_not_log_object_changes(self):
        policy = self._policy_with_objects()
        count = len(policy.message_ids)
        policy.object_ids[0].write({"sum_insured": 1})
        self.assertEqual(len(policy.message_ids), count)

    def test_objects_locked_with_closed_policy(self):
        policy = self._create_policy(
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            object_ids=[(0, 0, {"name": "Old truck", "sum_insured": 1})],
        )
        policy.action_confirm()
        self.assertEqual(policy.state, "expired")
        with self.assertRaises(UserError):
            policy.object_ids.write({"sum_insured": 2})
        with self.assertRaises(UserError):
            self.env["insurance.policy.object"].create({"policy_id": policy.id, "name": "New"})

    def test_insured_item_access(self):
        item = self.env["insurance.insured.item"].with_user(self.insurance_user).create(
            {"name": "Server room equipment", "item_type": "equipment"}
        )
        item.write({"location": "HQ"})
        with self.assertRaises(AccessError):
            item.unlink()
        item.with_user(self.insurance_manager).unlink()

    def test_multi_company_isolation(self):
        company_b = self.env["res.company"].create({"name": "Insurance company B"})
        policy_b = (
            self.env["insurance.policy"]
            .with_company(company_b)
            .create(
                self._policy_vals(
                    company_id=company_b.id,
                    branch_id=self.branch_fire.id,
                    object_ids=[(0, 0, {"name": "B object"})],
                )
            )
        )
        item_b = self.env["insurance.insured.item"].create({"name": "B item", "company_id": company_b.id})
        Policy = self.env["insurance.policy"].with_user(self.insurance_user)
        self.assertFalse(Policy.search([("id", "=", policy_b.id)]))
        self.assertFalse(
            self.env["insurance.policy.object"]
            .with_user(self.insurance_user)
            .search([("id", "in", policy_b.object_ids.ids)])
        )
        self.assertFalse(
            self.env["insurance.insured.item"].with_user(self.insurance_user).search([("id", "=", item_b.id)])
        )
        user_b = new_test_user(
            self.env,
            login="ins_user_b",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=company_b.id,
            company_ids=[company_b.id],
        )
        self.assertEqual(self.env["insurance.policy"].with_user(user_b).search([("id", "=", policy_b.id)]), policy_b)
