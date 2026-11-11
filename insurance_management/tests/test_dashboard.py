from datetime import date

from odoo import Command
from odoo.tests import tagged

from .test_claims import InsuranceClaimCommon


@tagged("post_install", "-at_install")
class TestDashboard(InsuranceClaimCommon):
    def test_figures_and_actions(self):
        today = date(self.year, 6, 1)
        expiring = self._policy(date_from=date(self.year - 1, 7, 1), date_to=date(self.year, 6, 20))
        expiring._apply_lifecycle_state(today)
        self.assertEqual(expiring.state, "expiring")
        self._policy(policy_number="ACC-2")
        claim = self._claim(self._policy(policy_number="ACC-3", object_ids=[Command.create({"name": "Truck"})]))
        claim.action_approve()
        dashboard = self.env["insurance.dashboard"].with_context(insurance_today=today).create({})
        self.assertEqual(dashboard.expiring_30_count, 1)
        self.assertEqual(dashboard.expiring_90_count, 1)
        self.assertEqual(dashboard.open_claim_count, 1)
        self.assertEqual(dashboard.claims_to_collect, 450000)
        action = dashboard.with_context(dashboard_key="expiring_30").action_open()
        self.assertEqual(action["res_model"], "insurance.policy")
        self.assertEqual(self.env["insurance.policy"].search(action["domain"]), expiring)
        action = dashboard.with_context(dashboard_key="claims_to_collect").action_open()
        self.assertEqual(self.env["insurance.claim"].search(action["domain"]), claim)
        opened = self.env["insurance.dashboard"].action_open_dashboard()
        self.assertEqual(opened["res_model"], "insurance.dashboard")
        self.assertTrue(opened["res_id"])
