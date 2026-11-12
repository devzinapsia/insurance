from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon

from ..hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestFleet(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("fleet.fleet_group_manager")
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Pickup", "brand_id": brand.id})
        Vehicle = cls.env["fleet.vehicle"]
        cls.truck = Vehicle.create({"model_id": model.id, "license_plate": "AB 123 CD", "vin_sn": "CH-0001", "company_id": cls.company.id})
        cls.van = Vehicle.create({"model_id": model.id, "license_plate": "XY-999-ZZ", "company_id": cls.company.id})
        cls.twin_1 = Vehicle.create({"model_id": model.id, "license_plate": "TW111", "company_id": cls.company.id})
        cls.twin_2 = Vehicle.create({"model_id": model.id, "license_plate": "tw 111", "company_id": cls.company.id})
        cls.archived = Vehicle.create({"model_id": model.id, "license_plate": "OLD001", "company_id": cls.company.id, "active": False})

    def _vehicle_policy(self, objects, **values):
        values.setdefault("object_ids", [Command.create(vals) for vals in objects])
        return self._policy(**values)

    def test_auto_link_by_normalized_plate_or_chassis(self):
        policy = self._vehicle_policy(
            [
                {"name": "Truck", "license_plate": "ab123cd"},
                {"name": "By chassis", "chassis_number": "ch 0001"},
                {"name": "Twin", "license_plate": "TW-111"},
                {"name": "Archived", "license_plate": "OLD 001"},
                {"name": "Unknown", "license_plate": "ZZ000ZZ"},
            ]
        )
        objects = {o.name: o for o in policy.object_ids}
        self.assertEqual(objects["Truck"].vehicle_id, self.truck)
        self.assertEqual(objects["By chassis"].vehicle_id, self.truck)
        self.assertFalse(objects["Twin"].vehicle_id)
        self.assertFalse(objects["Archived"].vehicle_id)
        self.assertFalse(objects["Unknown"].vehicle_id)

    def test_post_init_hook_links_existing_objects_and_reports(self):
        policy = self._vehicle_policy([{"name": "Van", "license_plate": "xy999zz"}, {"name": "Twin", "license_plate": "TW111"}])
        self.env.cr.execute("UPDATE insurance_policy_object SET vehicle_id = NULL WHERE policy_id = %s", (policy.id,))
        policy.object_ids.invalidate_recordset(["vehicle_id"])
        post_init_hook(self.env)
        van = policy.object_ids.filtered(lambda o: o.name == "Van")
        self.assertEqual(van.vehicle_id, self.van)
        self.assertTrue(policy.message_ids.filtered(lambda m: "several vehicles" in (m.body or "")))

    def test_renewal_and_endorsement_keep_the_vehicle(self):
        policy = self._vehicle_policy([{"name": "Manual link", "vehicle_id": self.van.id}])
        self.assertEqual(policy.object_ids.vehicle_id, self.van)
        renewal = self.env["insurance.policy"].create(policy._prepare_renewal_vals())
        self.assertEqual(renewal.object_ids.vehicle_id, self.van)
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": policy.id,
                "type_id": self.env.ref("insurance_management.insurance_endorsement_type_add_object").id,
                "effective_date": date(self.year, 2, 1),
                "line_ids": [Command.create({"operation": "add", "name": "New truck", "vehicle_id": self.truck.id})],
            }
        )
        endorsement.action_confirm()
        self.assertIn(self.truck, policy.object_ids.vehicle_id)

    def test_branch_requires_a_vehicle(self):
        self.branch.requires_fleet_vehicle = True
        with self.assertRaisesRegex(UserError, "requires a fleet vehicle"):
            self._vehicle_policy([{"name": "Unknown", "license_plate": "ZZ000ZZ"}])
        policy = self._vehicle_policy([{"name": "Truck", "license_plate": "AB123CD"}], policy_number="ACC-2")
        self.assertEqual(policy.state, "in_force")

    def test_vehicle_insurance_history_and_insured_today(self):
        policy = self._vehicle_policy([{"name": "Truck", "license_plate": "AB123CD"}])
        today = date(self.year, 6, 1)
        truck = self.truck.with_context(insurance_today=today)
        self.assertTrue(truck.insured_today)
        self.assertEqual(truck.insurance_policy_id, policy)
        self.assertEqual(truck.insurance_policy_count, 1)
        Vehicle = self.env["fleet.vehicle"].with_context(insurance_today=today)
        self.assertIn(self.truck, Vehicle.search([("insured_today", "=", True)]))
        self.assertIn(self.van, Vehicle.search([("insured_today", "=", False)]))
        self.assertFalse(self.van.with_context(insurance_today=today).insured_today)
        action = self.truck.action_view_insurance_policies()
        self.assertEqual(self.env["insurance.policy"].search(action["domain"]), policy)
        dashboard = self.env["insurance.dashboard"].with_context(insurance_today=today).create({})
        self.assertEqual(dashboard.uninsured_vehicle_count, 3)

    def test_claim_from_the_vehicle(self):
        policy = self._vehicle_policy([{"name": "Truck", "license_plate": "AB123CD"}])
        claim = self.env["insurance.claim"].new({"vehicle_id": self.truck.id, "date_occurred": date(self.year, 5, 5)})
        claim._onchange_vehicle_id()
        self.assertEqual(claim.policy_id, policy)
        self.assertEqual(claim.object_id, policy.object_ids)
        saved = self.env["insurance.claim"].create({"policy_id": policy.id, "object_id": policy.object_ids.id})
        self.assertEqual(saved.vehicle_id, self.truck)
        self.env.invalidate_all()
        self.assertEqual(self.truck.insurance_claim_count, 1)

    def test_insurance_user_without_fleet_rights_reads_the_vehicle(self):
        user = new_test_user(
            self.env, login="ins_nofleet",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        policy = self._vehicle_policy([{"name": "Truck", "license_plate": "AB123CD"}])
        data = policy.object_ids.with_user(user).web_read({"vehicle_id": {"fields": {"display_name": {}}}})
        self.assertEqual(data[0]["vehicle_id"]["id"], self.truck.id)

    def test_link_vehicle_by_hand_on_a_confirmed_policy(self):
        policy = self._vehicle_policy([{"name": "Unknown", "license_plate": "ZZ000ZZ"}])
        self.assertEqual(policy.state, "in_force")
        action = policy.action_open_vehicle_link()
        wizard = self.env["insurance.policy.vehicle.link"].with_context(**action["context"]).create({})
        self.assertEqual(wizard.line_ids.object_id, policy.object_ids)
        wizard.line_ids.vehicle_id = self.van
        wizard.action_confirm()
        self.assertEqual(policy.object_ids.vehicle_id, self.van)
        self.assertTrue(policy.message_ids.filtered(lambda m: "linked by hand" in (m.body or "")))
        # Still no other change without an endorsement.
        with self.assertRaises(UserError):
            policy.object_ids.license_plate = "CHANGED"
        # Only on confirmed vehicle policies.
        fire = self._policy(policy_number="ACC-9", branch_id=self.env.ref("insurance_management.insurance_branch_fire").id)
        with self.assertRaises(UserError):
            fire.action_open_vehicle_link()
