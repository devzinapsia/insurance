from freezegun import freeze_time

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestResPartnerInsurance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.insurer = Partner.create({"name": "Insurer SA", "is_company": True, "is_insurer": True})
        cls.producer = Partner.create({"name": "Producer", "is_insurance_producer": True})
        cls.both = Partner.create(
            {"name": "Insurer and producer", "is_insurer": True, "is_insurance_producer": True}
        )
        cls.other = Partner.create({"name": "Plain contact"})
        cls.all_partners = cls.insurer | cls.producer | cls.both | cls.other

    def test_flags_default_false(self):
        self.assertFalse(self.other.is_insurer)
        self.assertFalse(self.other.is_insurance_producer)

    def test_insurers_and_producers_filters(self):
        """The search filters 'Insurers' and 'Producers' select the marked contacts."""
        Partner = self.env["res.partner"]
        insurers = Partner.search([("is_insurer", "=", True), ("id", "in", self.all_partners.ids)])
        producers = Partner.search(
            [("is_insurance_producer", "=", True), ("id", "in", self.all_partners.ids)]
        )
        self.assertEqual(insurers, self.insurer | self.both)
        self.assertEqual(producers, self.producer | self.both)

    def test_flags_searchable_by_plain_employee(self):
        """The flags carry no group, so other apps reading partners never fail."""
        employee = new_test_user(self.env, login="flag_employee", groups="base.group_user")
        partners = (
            self.env["res.partner"]
            .with_user(employee)
            .search_read([("id", "in", self.all_partners.ids)], ["is_insurer", "is_insurance_producer"])
        )
        self.assertEqual(len(partners), 4)

    def test_search_filters_in_view(self):
        arch = self.env["res.partner"].get_view(view_type="search")["arch"]
        self.assertIn('name="insurers"', arch)
        self.assertIn('name="insurance_producers"', arch)


@tagged("post_install", "-at_install")
class TestResPartnerPolicyButton(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.insurer = Partner.create({"name": "Button insurer", "is_insurer": True})
        cls.producer = Partner.create({"name": "Button producer", "is_insurance_producer": True})
        cls.branch = cls.env.ref("insurance_management.insurance_branch_motor")

    def _policy(self, number, **values):
        vals = {
            "policy_number": number,
            "branch_id": self.branch.id,
            "insurer_id": self.insurer.id,
            "producer_id": self.producer.id,
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        }
        vals.update(values)
        return self.env["insurance.policy"].create(vals)

    def test_policy_count_and_action(self):
        with freeze_time("2026-06-15"):
            in_force = self._policy("P1")
            in_force.action_confirm()
            self._policy("P2")  # draft, not counted
            expired = self._policy("P3", date_from="2025-01-01", date_to="2025-12-31")
            expired.action_confirm()
            self.insurer.invalidate_recordset(["insurance_policy_count"])
            self.producer.invalidate_recordset(["insurance_policy_count"])
            self.assertEqual(self.insurer.insurance_policy_count, 1)
            self.assertEqual(self.producer.insurance_policy_count, 1)
            action = self.insurer.action_view_insurance_policies()
            self.assertEqual(action["res_model"], "insurance.policy")
            self.assertEqual(
                self.env["insurance.policy"].search(action["domain"]).sorted("policy_number").mapped("policy_number"),
                ["P1", "P2", "P3"],
            )
            self.assertEqual(action["context"], {"search_default_in_force": 1})
