from odoo import Command
from odoo.tests import tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon


@tagged("post_install", "-at_install")
class TestSuretySaleOrder(InsuranceAccountingCommon):
    def test_surety_linked_to_the_sale_order(self):
        self.env.user.group_ids |= self.env.ref("sales_team.group_sale_manager")
        self.beneficiary = self.env["res.partner"].create({"name": "Client", "is_company": True})
        record = self.env["sale.order"].create({"partner_id": self.beneficiary.id})
        policy = self._policy(
            branch_id=self.env.ref("insurance_management.insurance_branch_surety").id,
            surety_beneficiary_id=self.beneficiary.id,
            surety_sale_order_id=record.id,
            object_ids=[Command.create({"name": "Guarantee"})],
        )
        self.assertEqual(record.insurance_surety_count, 1)
        action = record.action_view_insurance_sureties()
        self.assertEqual(self.env["insurance.policy"].search(action["domain"]), policy)
        renewal = self.env["insurance.policy"].sudo().create(policy._prepare_renewal_vals())
        self.assertEqual(renewal.surety_sale_order_id, record)
