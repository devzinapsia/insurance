from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestInsuranceSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Insurance company B"})
        cls.insurance_user = new_test_user(
            cls.env,
            login="insurance_user",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=cls.company_a.id,
            company_ids=[cls.company_a.id],
        )
        cls.insurance_manager = new_test_user(
            cls.env,
            login="insurance_manager",
            groups="base.group_user,insurance_management.group_insurance_manager",
            company_id=cls.company_a.id,
            company_ids=[cls.company_a.id],
        )
        cls.employee = new_test_user(cls.env, login="plain_employee", groups="base.group_user")
        cls.branch_shared = cls.env.ref("insurance_management.insurance_branch_fire")
        cls.branch_b = cls.env["insurance.branch"].create(
            {"name": "Company B only", "company_id": cls.company_b.id}
        )

    def test_group_hierarchy(self):
        user_group = self.env.ref("insurance_management.group_insurance_user")
        manager_group = self.env.ref("insurance_management.group_insurance_manager")
        self.assertIn(user_group, manager_group.all_implied_ids)
        self.assertTrue(self.insurance_manager.has_group("insurance_management.group_insurance_user"))
        self.assertFalse(self.insurance_user.has_group("insurance_management.group_insurance_manager"))
        self.assertTrue(
            self.env.ref("base.user_admin").has_group("insurance_management.group_insurance_manager")
        )

    def test_user_reads_branches_but_cannot_configure(self):
        Branch = self.env["insurance.branch"].with_user(self.insurance_user)
        self.assertTrue(Branch.search([("id", "=", self.branch_shared.id)]))
        self.branch_shared.with_user(self.insurance_user).read(["name", "alert_days"])
        with self.assertRaises(AccessError):
            Branch.create({"name": "Not allowed"})
        with self.assertRaises(AccessError):
            self.branch_shared.with_user(self.insurance_user).write({"alert_days": "10"})
        with self.assertRaises(AccessError):
            self.branch_shared.with_user(self.insurance_user).unlink()

    def test_manager_configures_branches(self):
        Branch = self.env["insurance.branch"].with_user(self.insurance_manager)
        branch = Branch.create({"name": "Manager branch", "alert_days": "20"})
        branch.write({"alert_days": "20,5"})
        self.assertEqual(branch.alert_days, "20,5")
        branch.unlink()

    def test_employee_without_insurance_group_has_no_access(self):
        with self.assertRaises(AccessError):
            self.env["insurance.branch"].with_user(self.employee).search([])

    def test_branch_multi_company_rule(self):
        Branch = self.env["insurance.branch"].with_user(self.insurance_user)
        visible = Branch.search([("id", "in", (self.branch_shared | self.branch_b).ids)])
        self.assertEqual(visible, self.branch_shared, "Company B branch must be hidden")
        user_b = new_test_user(
            self.env,
            login="insurance_user_b",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=self.company_b.id,
            company_ids=[self.company_b.id],
        )
        visible_b = (
            self.env["insurance.branch"]
            .with_user(user_b)
            .search([("id", "in", (self.branch_shared | self.branch_b).ids)])
        )
        self.assertEqual(visible_b, self.branch_shared | self.branch_b)
