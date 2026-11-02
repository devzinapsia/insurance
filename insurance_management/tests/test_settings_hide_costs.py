from datetime import date

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import InsuranceCommon


@tagged("post_install", "-at_install")
@freeze_time("2026-06-01")
class TestSettingsAndHideCosts(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls._create_policy(
            object_ids=[(0, 0, {"name": "Truck", "sum_insured": 100000})],
            deductible_type="amount",
            deductible_amount=5000,
        )
        cls.see_amounts = cls.env.ref("insurance_management.group_insurance_see_amounts")
        cls.user_group = cls.env.ref("insurance_management.group_insurance_user")

    def _save_settings(self, user=None, **values):
        Settings = self.env["insurance.settings"].with_user(user or self.insurance_manager)
        settings = Settings.create(values)
        settings.action_save()
        return settings

    def test_users_see_amounts_by_default(self):
        self.assertIn(self.see_amounts, self.user_group.all_implied_ids)
        values = self.policy.with_user(self.insurance_user).read(["premium", "premium_total"])[0]
        self.assertEqual(values["premium_total"], 1210.0)

    def test_hide_costs_enforced_on_server(self):
        self._save_settings(hide_costs=True)
        self.assertNotIn(self.see_amounts, self.user_group.all_implied_ids)
        user = self.insurance_user
        self.assertFalse(user.has_group("insurance_management.group_insurance_see_amounts"))
        Policy = self.env["insurance.policy"].with_user(user)
        for fname in ("premium", "premium_total", "sum_insured_total", "deductible_amount", "deductible_percent"):
            with self.subTest(field=fname):
                with self.assertRaises(AccessError):
                    self.policy.with_user(user).read([fname])
                with self.assertRaises(AccessError):
                    Policy.search_read([("id", "=", self.policy.id)], [fname])
                with self.assertRaises(AccessError):
                    Policy.search([(fname, ">", 0)])
        with self.assertRaises(AccessError):
            self.policy.object_ids.with_user(user).read(["sum_insured"])
        with self.assertRaises(AccessError):
            self.policy.with_user(user).write({"premium_total": 1})
        # Other fields stay readable and editable, and views drop the amounts.
        self.policy.with_user(user).write({"note": "<p>ok</p>"})
        arch = Policy.get_view(view_type="form")["arch"]
        self.assertNotIn('name="premium_total"', arch)
        # The administrator always sees them.
        self.assertEqual(self.policy.with_user(self.insurance_manager).read(["premium_total"])[0]["premium_total"], 1210.0)

    def test_see_amounts_per_user_and_back(self):
        self._save_settings(hide_costs=True)
        trusted = new_test_user(
            self.env,
            login="trusted",
            groups="base.group_user,insurance_management.group_insurance_user,insurance_management.group_insurance_see_amounts",
        )
        self.assertEqual(self.policy.with_user(trusted).read(["premium_total"])[0]["premium_total"], 1210.0)
        self._save_settings(hide_costs=False)
        self.assertEqual(self.policy.with_user(self.insurance_user).read(["premium_total"])[0]["premium_total"], 1210.0)

    def test_hidden_amount_trackings(self):
        self.policy.action_confirm()
        self.env.cr.flush()
        self.policy.write({"premium_total": 2000, "renewal_type": "renew"})
        self.env.cr.flush()
        self._save_settings(hide_costs=True)
        self.policy.invalidate_recordset(["message_ids"])
        trackings = self.policy.message_ids.sudo().tracking_value_ids
        self.assertTrue(trackings.filtered(lambda t: t.field_id.name == "premium_total"))
        visible = trackings._filter_has_field_access(self.env(user=self.insurance_user))
        self.assertFalse(visible.filtered(lambda t: t.field_id.name == "premium_total"))
        self.assertTrue(visible.filtered(lambda t: t.field_id.name == "renewal_type"))

    def test_user_without_amounts_can_still_work(self):
        """Renewing and adding objects copy / log amounts as superuser."""
        self._save_settings(hide_costs=True)
        user = self.insurance_user
        self.policy.action_confirm()
        self.policy.with_user(user).object_ids.create(
            {"policy_id": self.policy.id, "name": "Van"}
        )
        self.policy.with_context(insurance_lifecycle_write=True).write({"state": "expiring"})
        action = self.policy.with_user(user).action_renew()
        renewal = self.env["insurance.policy"].browse(action["res_id"])
        self.assertEqual(renewal.deductible_amount, 5000)
        self.assertEqual(sorted(renewal.object_ids.mapped("sum_insured")), [0.0, 100000.0])

    def test_settings_saved_per_company(self):
        self._save_settings(
            alert_days=" 7,30 ,15",
            notify_user_ids=[(6, 0, self.insurance_user.ids)],
            min_duration_months=2,
            max_duration_months=24,
            duration_check="warning",
            coverage_time="0",
            non_renewal_send_mode="automatic",
            non_renewal_days=25,
            batch_size=50,
        )
        company = self.company
        self.assertEqual(company.insurance_alert_days, "30,15,7")
        self.assertEqual(company.insurance_notify_user_ids, self.insurance_user)
        self.assertEqual(
            (company.insurance_min_duration_months, company.insurance_max_duration_months), (2, 24)
        )
        self.assertEqual(company.insurance_duration_check, "warning")
        self.assertEqual(company.insurance_coverage_time, "0")
        self.assertEqual(company.insurance_non_renewal_send_mode, "automatic")
        self.assertEqual(company.insurance_non_renewal_days, 25)
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param("insurance_management.cron_batch_size"), "50"
        )
        # New policies take the non-renewal defaults of the company.
        new_policy = self._create_policy(policy_number="NEW")
        self.assertEqual((new_policy.non_renewal_send_mode, new_policy.non_renewal_days), ("automatic", 25))
        # The form reads them back.
        settings = self.env["insurance.settings"].with_user(self.insurance_manager).create({})
        self.assertEqual(settings.alert_days, "30,15,7")
        self.assertTrue(settings.duration_check == "warning" and not settings.hide_costs)

    def test_only_administrator_changes_settings(self):
        with self.assertRaises(AccessError):
            self._save_settings(user=self.insurance_user, alert_days="5")
        with self.assertRaises(AccessError):
            self.env["insurance.settings"].with_user(self.insurance_manager).create({}).with_user(
                self.insurance_user
            ).action_save()

    def test_coverage_time_in_emails(self):
        self.assertIn("12:00", self.policy._get_mail_validity())
        self.company.insurance_coverage_time = "0"
        text = self.policy.with_context(lang="en_US")._get_mail_validity()
        self.assertIn("0:00", text)
        self.assertEqual(self.policy.date_to, date(2026, 12, 31))
        self.assertIn("2027", text, "With 0:00 the coverage ends at 0:00 of the day after")
