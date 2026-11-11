from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon


@tagged("post_install", "-at_install")
class TestHr(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("hr.group_hr_user")
        cls.person_branch = cls.env.ref("insurance_management.insurance_branch_personal_accident")
        cls.employee = cls.env["hr.employee"].create({"name": "Ana Example", "company_id": cls.company.id})
        cls.other = cls.env["hr.employee"].create({"name": "Other Employee", "company_id": cls.company.id})

    def _person_policy(self, **values):
        values.setdefault("object_ids", [Command.create({"name": "Ana", "employee_id": self.employee.id})])
        return self._policy(branch_id=self.person_branch.id, **values)

    def test_history_claims_and_insured_today(self):
        policy = self._person_policy()
        today = date(self.year, 6, 1)
        employee = self.employee.with_context(insurance_today=today)
        self.assertTrue(employee.insured_today)
        self.assertEqual(employee.insurance_policy_count, 1)
        Employee = self.env["hr.employee"].with_context(insurance_today=today)
        self.assertIn(self.employee, Employee.search([("insured_today", "=", True)]))
        self.assertNotIn(self.other, Employee.search([("insured_today", "=", True)]))
        claim = self.env["insurance.claim"].new({"employee_id": self.employee.id, "date_occurred": date(self.year, 4, 1)})
        claim._onchange_employee_id()
        self.assertEqual(claim.object_id, policy.object_ids)
        saved = self.env["insurance.claim"].create({"policy_id": policy.id, "object_id": policy.object_ids.id, "claim_type": "personal_accident"})
        self.assertEqual(saved.employee_id, self.employee)
        self.env.invalidate_all()
        self.assertEqual(self.employee.insurance_claim_count, 1)
        action = self.employee.action_view_insurance_policies()
        self.assertEqual(self.env["insurance.policy"].search(action["domain"]), policy)

    def test_renewal_and_endorsement_keep_the_employee(self):
        policy = self._person_policy()
        renewal = self.env["insurance.policy"].create(policy._prepare_renewal_vals())
        self.assertEqual(renewal.object_ids.employee_id, self.employee)
        endorsement = self.env["insurance.endorsement"].create(
            {
                "policy_id": policy.id,
                "type_id": self.env.ref("insurance_management.insurance_endorsement_type_add_object").id,
                "effective_date": date(self.year, 2, 1),
                "line_ids": [Command.create({"operation": "add", "name": "Other", "employee_id": self.other.id})],
            }
        )
        endorsement.action_confirm()
        self.assertIn(self.other, policy.object_ids.employee_id)

    def test_only_person_branches(self):
        with self.assertRaises(ValidationError):
            self._policy(object_ids=[Command.create({"name": "Ana", "employee_id": self.employee.id})])

    def test_insurance_user_without_hr_rights_reads_the_employee(self):
        user = new_test_user(
            self.env, login="ins_nohr",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        policy = self._person_policy()
        data = policy.object_ids.with_user(user).web_read({"employee_id": {"fields": {"display_name": {}}}})
        self.assertEqual(data[0]["employee_id"]["display_name"], "Ana Example")
