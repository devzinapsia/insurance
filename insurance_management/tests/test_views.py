from odoo.tests import new_test_user, tagged

from .common import InsuranceCommon

VIEW_TYPES = ["kanban", "list", "form", "calendar", "pivot", "graph", "search"]


@tagged("post_install", "-at_install")
class TestViews(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.no_amounts_user = new_test_user(
            cls.env, login="no_amounts", groups="base.group_user,insurance_management.group_insurance_user"
        )
        cls.env.ref("insurance_management.group_insurance_user").sudo()._remove_group(
            cls.env.ref("insurance_management.group_insurance_see_amounts").sudo()
        )

    def test_policy_views_load_for_every_profile(self):
        action = self.env.ref("insurance_management.insurance_policy_action")
        self.assertEqual(action.view_mode, "kanban,list,form,calendar,pivot,graph,activity")
        for user in (self.insurance_manager, self.insurance_user, self.no_amounts_user):
            views = self.env["insurance.policy"].with_user(user).get_views([(False, vt) for vt in VIEW_TYPES])
            with self.subTest(user=user.login):
                self.assertEqual(set(views["views"]), set(VIEW_TYPES))
                kanban = views["views"]["kanban"]["arch"]
                self.assertIn('default_group_by="state"', kanban)
                calendar = views["views"]["calendar"]["arch"]
                self.assertIn('date_start="date_to"', calendar)
        hidden = self.env["insurance.policy"].with_user(self.no_amounts_user).get_views([(False, "pivot"), (False, "form")])
        self.assertNotIn("premium_total", hidden["views"]["pivot"]["arch"])
        self.assertNotIn('name="premium_total"', hidden["views"]["form"]["arch"])

    def test_section_10_filters(self):
        arch = self.env["insurance.policy"].get_view(view_type="search")["arch"]
        for name in (
            "in_force",
            "expire_30_days",
            "expired_not_renewed",
            "expires_today",
            "group_by_branch",
            "group_by_insurer",
            "group_by_producer",
        ):
            with self.subTest(filter=name):
                self.assertIn(f'name="{name}"', arch)

    def test_upcoming_expirations_report(self):
        action = self.env.ref("insurance_management.insurance_policy_expiration_action")
        self.assertIn("search_default_expire_30_days", action.context)
        views = self.env["insurance.policy"].with_user(self.insurance_user).get_views(
            [(self.env.ref("insurance_management.insurance_policy_view_list_expiration").id, "list")]
        )
        self.assertIn('default_order="date_to, id"', views["views"]["list"]["arch"])

    def test_menus_by_group(self):
        Menu = self.env["ir.ui.menu"]
        configuration = self.env.ref("insurance_management.menu_insurance_configuration")
        policies = self.env.ref("insurance_management.menu_insurance_policy")
        reporting = self.env.ref("insurance_management.menu_insurance_report_expiration")
        user_menus = Menu.with_user(self.insurance_user)._visible_menu_ids()
        manager_menus = Menu.with_user(self.insurance_manager)._visible_menu_ids()
        self.assertIn(policies.id, user_menus)
        self.assertIn(reporting.id, user_menus)
        self.assertNotIn(configuration.id, user_menus)
        self.assertIn(configuration.id, manager_menus)
        employee = new_test_user(self.env, login="menu_employee", groups="base.group_user")
        self.assertNotIn(
            self.env.ref("insurance_management.menu_insurance_root").id,
            Menu.with_user(employee)._visible_menu_ids(),
        )

    def test_other_views_load(self):
        for model in ("insurance.branch", "insurance.insured.item", "insurance.document.type", "insurance.settings"):
            with self.subTest(model=model):
                self.env[model].with_user(self.insurance_manager).get_views([(False, "form"), (False, "search")])
        self.env["res.partner"].with_user(self.insurance_user).get_views([(False, "form")])

    def test_tag_color_picker(self):
        """Creating a tag from the policy shows the color palette, not a number."""
        views = self.env["insurance.policy.tag"].with_user(self.insurance_user).get_views(
            [(False, "form"), (False, "list")]
        )
        self.assertIn('widget="color_picker"', views["views"]["form"]["arch"])
        self.assertIn('widget="color_picker"', views["views"]["list"]["arch"])
