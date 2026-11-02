import re
from datetime import date

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import InsuranceCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-06-01")
class TestReports(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls._create_policy(
            coverage="<p>All risks with deductible</p>",
            deductible_type="amount",
            deductible_amount=86420.97,
            object_ids=[
                (0, 0, {"name": "Truck", "license_plate": "AB123CD", "sum_insured": 9876543.21, "coverage": "All risks"}),
                (0, 0, {"name": "Van", "license_plate": "AC456EF", "sum_insured": 65432}),
            ],
        )
        cls.policy.action_confirm()
        cls.policy.object_ids.filtered(lambda o: o.name == "Van")._exclude(date(2026, 5, 1), "Vehicle sold")
        cls.other = cls._create_policy(policy_number="POL-002", date_from=date(2026, 2, 1), date_to=date(2027, 1, 31))
        cls.other.action_confirm()

    @staticmethod
    def _digits(html):
        """Report text with thousands/decimal separators removed."""
        return re.sub(r"[.,\s\xa0]", "", html)

    def _html(self, report_xmlid, records, user):
        html, _ = (
            self.env["ir.actions.report"]
            .with_user(user)
            .with_context(lang="en_US")
            ._render_qweb_html(report_xmlid, records.ids)
        )
        return html.decode()

    def test_policy_sheet(self):
        html = self._html("insurance_management.action_report_insurance_policy", self.policy, self.insurance_user)
        for text in ("POL-001", "Truck", "AB123CD", "Van", "Vehicle sold", "All risks with deductible", "Insurer SA", "Producer"):
            self.assertIn(text, html)
        self.assertIn("987654321", self._digits(html))
        self.assertIn("8642097", self._digits(html))
        # Empty values never show the template's example text.
        self.assertNotIn("01/06/2026", html)
        self.assertNotIn("SEG/2026/0001</span> -", html.replace(self.policy.name, "X"))

    def test_policy_sheet_without_amounts(self):
        hidden = new_test_user(
            self.env, login="sheet_no_amounts", groups="base.group_user,insurance_management.group_insurance_user"
        )
        self.env.ref("insurance_management.group_insurance_user").sudo()._remove_group(
            self.env.ref("insurance_management.group_insurance_see_amounts").sudo()
        )
        html = self._html("insurance_management.action_report_insurance_policy", self.policy, hidden)
        self.assertIn("Truck", html)
        for amount in ("987654321", "8642097", "121000"):
            self.assertNotIn(amount, self._digits(html))
        html_list = self._html("insurance_management.action_report_insurance_policy_list", self.policy | self.other, hidden)
        self.assertNotIn("987654321", self._digits(html_list))

    def test_policies_in_force_list(self):
        html = self._html("insurance_management.action_report_insurance_policy_list", self.other | self.policy, self.insurance_user)
        self.assertLess(html.index("POL-001"), html.index("POL-002"), "Ordered by end date")
        action = self.env["insurance.policy"].with_user(self.insurance_user).action_print_policies_in_force()
        self.assertEqual(action["report_name"], "insurance_management.report_insurance_policy_list")
        self.assertTrue({self.policy.id, self.other.id} <= set(action["context"]["active_ids"]))

    def test_nothing_to_print(self):
        self.env["insurance.policy"].search([("state", "in", ("in_force", "expiring"))]).with_context(
            insurance_lifecycle_write=True
        ).write({"state": "cancelled"})
        with self.assertRaises(UserError):
            self.env["insurance.policy"].action_print_policies_in_force()
