from datetime import date

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import InsuranceCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-06-15")
class TestEndorsements(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.producer_2 = cls.env["res.partner"].create({"name": "Second producer", "is_insurance_producer": True})

    def _confirmed_policy(self, **values):
        vals = {
            "object_ids": [
                (0, 0, {"name": "Truck", "license_plate": "AB123CD", "sum_insured": 100000}),
                (0, 0, {"name": "Van", "license_plate": "AC456EF", "sum_insured": 50000}),
            ]
        }
        vals.update(values)
        policy = self._create_policy(**vals)
        policy.action_confirm()
        return policy

    def test_initial_endorsement_types_described(self):
        types = self.env["insurance.endorsement.type"].search([])
        seeded = types.filtered(lambda t: t.get_external_id()[t.id].startswith("insurance_management."))
        self.assertEqual(len(seeded), 8)
        self.assertTrue(all(seeded.with_context(lang="en_US").mapped("description")))
        self.env["res.lang"]._activate_lang("es_AR")
        self.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        sold = self.env.ref("insurance_management.insurance_endorsement_type_remove_object")
        self.assertIn("se vende un vehículo de la flota", sold.with_context(lang="es_AR").description)

    def test_only_on_policies_in_force_or_expiring(self):
        draft = self._create_policy(policy_number="DRAFT")
        with self.assertRaises(UserError):
            self._endorse(draft, "data_change", description="Draft")
        expired = self._create_policy(policy_number="OLD", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        expired.action_confirm()
        with self.assertRaises(UserError):
            self._endorse(expired, "data_change", effective_date=date(2025, 6, 1), description="Expired")
        with self.assertRaises(UserError):
            draft.action_new_endorsement()

    def test_effective_date_within_validity(self):
        policy = self._confirmed_policy()
        with self.assertRaises(ValidationError):
            self._endorse(policy, "data_change", effective_date=date(2027, 1, 15), description="Out of range")

    def test_add_remove_and_change_objects_keep_history(self):
        policy = self._confirmed_policy()
        truck = policy.object_ids.filtered(lambda o: o.name == "Truck")
        van = policy.object_ids.filtered(lambda o: o.name == "Van")
        added = self._endorse(
            policy, "add_object", user=self.insurance_user, effective_date=date(2026, 3, 1),
            lines=[{"operation": "add", "name": "Car", "license_plate": "AD789GH", "sum_insured": 30000}],
        )
        removed = self._endorse(
            policy, "remove_object", effective_date=date(2026, 4, 1),
            lines=[{"operation": "remove", "object_id": van.id, "reason": "Sold"}],
        )
        changed = self._endorse(
            policy, "increase_sum", effective_date=date(2026, 5, 1),
            lines=[{"operation": "change", "object_id": truck.id, "sum_insured": 120000}],
        )
        car = policy.object_ids.filtered(lambda o: o.name == "Car")
        self.assertEqual((car.date_start, car.endorsement_in_id), (date(2026, 3, 1), added))
        self.assertEqual((van.state, van.date_end, van.endorsement_out_id), ("excluded", date(2026, 4, 1), removed))
        self.assertEqual(changed.line_ids.old_sum_insured, 100000)
        self.assertEqual(truck.sum_insured, 120000)
        self.assertEqual(len(policy.object_ids), 3, "Nothing is deleted")
        self.assertEqual(policy.sum_insured_total, 150000)
        self.assertEqual(policy.endorsement_count, 3)
        self.assertTrue(added.name.startswith(policy.name + "/E"))

    def test_lines_must_match_the_type(self):
        policy = self._confirmed_policy()
        with self.assertRaises(UserError):
            self._endorse(policy, "add_object")
        with self.assertRaises(UserError):
            self._endorse(
                policy, "remove_object",
                lines=[{"operation": "add", "name": "Wrong operation"}],
            )

    def test_extension_coverage_and_data_change(self):
        policy = self._confirmed_policy()
        self._endorse(policy, "extension", effective_date=date(2026, 12, 1), new_date_to=date(2027, 2, 28))
        self.assertEqual(policy.date_to, date(2027, 2, 28), "An extension may exceed the maximum duration")
        self._endorse(policy, "coverage_change", new_coverage="<p>Third party only</p>")
        self.assertIn("Third party only", policy.coverage)
        self._endorse(policy, "data_change", new_producer_id=self.producer_2.id)
        self.assertEqual(policy.producer_id, self.producer_2)
        with self.assertRaises(UserError):
            self._endorse(policy, "extension", new_date_to=date(2027, 1, 1))

    def test_cancellation(self):
        policy = self._confirmed_policy()
        self._endorse(policy, "cancellation", effective_date=date(2026, 6, 15), description="Vehicles sold")
        self.assertEqual(policy.state, "cancelled")
        self.assertFalse(policy.covered_today)
        self.assertTrue(policy.is_locked)
        self.assertFalse(self.env["insurance.policy"].search([("id", "=", policy.id), ("state", "in", ("in_force", "expiring"))]))

    def test_premium_with_endorsements(self):
        policy = self._confirmed_policy()
        self._endorse(policy, "data_change", description="Surcharge", premium_difference=300.0)
        self._endorse(policy, "data_change", description="Refund", premium_difference=-100.0)
        draft = self.env["insurance.endorsement"].create(
            {
                "policy_id": policy.id,
                "type_id": self.env.ref("insurance_management.insurance_endorsement_type_data_change").id,
                "effective_date": date(2026, 6, 1),
                "premium_difference": 999.0,
            }
        )
        self.assertEqual(policy.endorsement_premium_total, 200.0, "Only confirmed endorsements count")
        self.assertEqual(policy.premium_with_endorsements, 1410.0)
        draft.action_cancel()
        self.assertEqual(draft.state, "cancelled")

    def test_confirmed_endorsement_cannot_be_deleted(self):
        policy = self._confirmed_policy()
        endorsement = self._endorse(policy, "data_change", description="Kept")
        with self.assertRaises(UserError):
            endorsement.unlink()
        with self.assertRaises(UserError):
            endorsement.action_cancel()

    def test_endorsement_number_unique_per_policy(self):
        policy = self._confirmed_policy()
        self._endorse(policy, "data_change", description="A", endorsement_number="E-1")
        other = self._confirmed_policy(policy_number="POL-OTHER")
        self._endorse(other, "data_change", description="B", endorsement_number="E-1")
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._endorse(policy, "data_change", description="C", endorsement_number="E-1")
                self.env.flush_all()

    def test_endorsement_types_managed_by_administrator(self):
        Type = self.env["insurance.endorsement.type"]
        self.assertEqual(Type.search_count([]), 8)
        with self.assertRaises(AccessError):
            Type.with_user(self.insurance_user).create({"name": "No", "kind": "data_change"})
        Type.with_user(self.insurance_manager).create({"name": "Yes", "kind": "data_change"})

    def test_hidden_premium_difference(self):
        self.env.ref("insurance_management.group_insurance_user").sudo()._remove_group(
            self.env.ref("insurance_management.group_insurance_see_amounts").sudo()
        )
        policy = self._confirmed_policy()
        endorsement = self._endorse(policy, "data_change", description="Hidden", premium_difference=50.0)
        with self.assertRaises(AccessError):
            endorsement.with_user(self.insurance_user).read(["premium_difference"])
        endorsement.with_user(self.insurance_user).read(["name", "state"])
