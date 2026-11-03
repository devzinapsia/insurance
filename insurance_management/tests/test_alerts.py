from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.insurance_management.models.insurance_policy import InsurancePolicy

from .common import InsuranceCommon

# All tests run "today" = 2026-06-01 unless frozen otherwise.
TODAY = date(2026, 6, 1)


@tagged("post_install", "-at_install")
class TestAlerts(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("en_US")
        cls.env["res.lang"]._activate_lang("es_AR")
        # Activating a language does not load the module terms (e.g. on a
        # fresh database, as odoo.sh builds do): load them explicitly.
        cls.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        cls.company.write({"insurance_alert_days": "60", "insurance_notify_user_ids": [(5, 0, 0)]})
        cls.branch.write({"alert_days": "30,15,7", "notify_user_ids": [(5, 0, 0)]})
        cls.branch_fire.write({"alert_days": False, "notify_user_ids": [(5, 0, 0)]})
        cls.responsible = new_test_user(
            cls.env, login="resp", name="Responsible", email="resp@example.com", lang="es_AR",
            groups="base.group_user,insurance_management.group_insurance_user",
        )
        cls.watcher = new_test_user(
            cls.env, login="watch", name="Watcher", email="watch@example.com", lang="en_US",
            groups="base.group_user,insurance_management.group_insurance_user",
        )
        cls.producer.email = "producer@example.com"
        cls.Policy = cls.env["insurance.policy"]

    def _policy(self, date_to, **values):
        """Confirmed policy of the motor branch (30,15,7) ending on date_to."""
        vals = {
            "date_from": date_to - timedelta(days=364),
            "date_to": date_to,
            "user_id": self.responsible.id,
            "object_ids": [(0, 0, {"name": f"Vehicle {i}", "license_plate": f"AA{i:03d}BB"}) for i in range(5)],
        }
        vals.update(values)
        with freeze_time(TODAY):
            policy = self._create_policy(**vals)
            policy.action_confirm()
        return policy

    def _run(self, day, policies=None):
        with freeze_time(day):
            policies = policies if policies is not None else self.Policy.search([("state", "in", ("in_force", "expiring"))])
            return self.Policy._process_expiry_batch(policies)

    def _mails(self, policy):
        """Alert emails of the policy (not Odoo's own follower notifications,
        such as "you have been assigned")."""
        return self.env["mail.mail"].search(
            [("model", "=", "insurance.policy"), ("res_id", "=", policy.id), ("is_notification", "=", False)]
        )

    def _notices(self, policy):
        return policy.alert_ids.filtered(lambda a: a.alert_type == "expiry_notice")

    # Parameters -------------------------------------------------------------

    def test_alert_days_hierarchy(self):
        """Policy > branch > settings."""
        fire = self._create_policy(branch_id=self.branch_fire.id)
        self.assertEqual(fire._get_alert_days(), [60], "Settings value")
        self.branch_fire.alert_days = "45, 10"
        self.assertEqual(fire._get_alert_days(), [45, 10], "Branch value")
        fire.alert_days = "20,5"
        self.assertEqual(fire._get_alert_days(), [20, 5], "Policy value")
        self.assertEqual(fire.effective_alert_days, "20,5")

    def test_notify_users_union(self):
        other = new_test_user(self.env, login="other", groups="base.group_user")
        portal = new_test_user(self.env, login="portal_u", groups="base.group_portal")
        self.company.insurance_notify_user_ids = self.watcher | other
        self.branch.notify_user_ids = other
        policy = self._create_policy(user_id=self.responsible.id, notify_user_ids=[(6, 0, (self.watcher | portal).ids)])
        self.assertEqual(policy._get_notify_users(), self.watcher | other | self.responsible)

    # Thresholds -------------------------------------------------------------

    def test_expiring_on_first_threshold_and_one_notice_per_threshold(self):
        policy = self._policy(date(2026, 7, 31))
        self.assertEqual(policy.state, "in_force")
        self._run(date(2026, 6, 30))  # 31 days left
        self.assertEqual(policy.state, "in_force")
        self.assertFalse(self._mails(policy))
        self._run(date(2026, 7, 1))  # 30 days left
        self.assertEqual(policy.state, "expiring")
        self.assertEqual(self._notices(policy).mapped("threshold_days"), [30])
        self.assertEqual(len(self._mails(policy)), 1, "Only the responsible is notified")
        self._run(date(2026, 7, 2))  # 29: nothing new
        self.assertEqual(len(self._notices(policy)), 1)
        self._run(date(2026, 7, 16))  # 15
        self._run(date(2026, 7, 24))  # 7
        self._run(date(2026, 7, 31))  # 0: expires today
        self.assertEqual(sorted(self._notices(policy).mapped("threshold_days")), [0, 7, 15, 30])
        self.assertEqual(len(self._mails(policy)), 4)
        self.assertEqual(policy.state, "expiring")

    def test_several_thresholds_crossed_send_one_notice(self):
        """Loaded with 10 days left and thresholds 30,15,7: one notice (15)
        and 30 marked as covered."""
        policy = self._policy(date(2026, 6, 11))
        self.assertEqual(policy.state, "expiring", "State is computed at confirmation")
        self.assertFalse(self._mails(policy), "Confirming sends nothing")
        self._run(TODAY)
        notices = self._notices(policy)
        self.assertEqual(sorted(notices.mapped("threshold_days")), [15, 30])
        self.assertEqual(notices.filtered("skipped").threshold_days, 30)
        self.assertEqual(notices.filtered(lambda a: not a.skipped).recipient_ids, self.responsible)
        self.assertEqual(len(self._mails(policy)), 1)

    def test_running_twice_the_same_day_duplicates_nothing(self):
        self.company.insurance_notify_user_ids = self.watcher
        policy = self._policy(date(2026, 6, 16))
        self._run(TODAY)
        self._run(TODAY)
        self.assertEqual(len(self._mails(policy)), 2, "One email per recipient, once")
        self.assertEqual(len(self._notices(policy).filtered(lambda a: not a.skipped)), 1)
        activity_type = self.env.ref("insurance_management.mail_activity_type_policy_expiry")
        self.assertEqual(len(policy.activity_ids.filtered(lambda a: a.activity_type_id == activity_type)), 1)

    def test_changing_end_date_restarts_alerts(self):
        policy = self._policy(date(2026, 6, 20))
        self._run(TODAY)  # 19 days left -> notice 30
        self.assertEqual(len(self._mails(policy)), 1)
        with freeze_time(TODAY):
            # Contract dates of a confirmed policy only change through an endorsement.
            policy.with_context(insurance_endorsement_write=True).write(
                {"date_from": date(2025, 9, 1), "date_to": date(2026, 8, 31)}
            )
        self.assertEqual(policy.state, "in_force", "Moving the end date away goes back to In force")
        self._run(date(2026, 8, 1))  # 30 days left for the new end date
        self.assertEqual(policy.state, "expiring")
        self.assertEqual(len(self._mails(policy)), 2, "The new end date gets its own notices")
        self.assertEqual(
            self._notices(policy).filtered(lambda a: a.date_to == date(2026, 8, 31)).threshold_days, 30
        )

    # Recipients, language and content ----------------------------------------

    def test_one_email_per_recipient_in_their_language(self):
        self.company.insurance_notify_user_ids = self.watcher
        policy = self._policy(date(2026, 6, 16))
        self._run(TODAY)
        mails = self._mails(policy)
        self.assertEqual(len(mails), 2)
        by_partner = {mail.recipient_ids: mail for mail in mails}
        spanish = by_partner[self.responsible.partner_id]
        english = by_partner[self.watcher.partner_id]
        self.assertIn("vence en 15 días", spanish.subject)
        self.assertIn("Hola Responsible", spanish.body_html)
        self.assertIn("expires in 15 days", english.subject)
        self.assertIn("Hello Watcher", english.body_html)
        self.assertEqual(spanish.email_from, policy.company_id.email_formatted or spanish.email_from)

    def test_notice_content(self):
        policy = self._policy(date(2026, 6, 2))  # tomorrow
        self._run(TODAY)
        mail = self._mails(policy)
        body = mail.body_html
        self.assertIn("vence mañana", mail.subject)
        self.assertIn(f"/mail/view?model=insurance.policy&amp;res_id={policy.id}", body)
        self.assertIn(policy.policy_number, body)
        self.assertIn(self.insurer.name, body)
        self.assertIn(self.producer.name, body)
        self.assertIn("A definir", body, "Renewal type")
        self.assertIn("(+2)", body, "Only the first three objects are listed")
        self.assertNotIn("1.210", body, "No amounts")
        self.assertIn("Qué hacer", body)

    def test_activity_for_responsible(self):
        policy = self._policy(date(2026, 6, 16))
        self._run(TODAY)
        activity = policy.activity_ids
        self.assertEqual(activity.user_id, self.responsible)
        self.assertEqual(activity.activity_type_id, self.env.ref("insurance_management.mail_activity_type_policy_expiry"))
        self.assertEqual(activity.date_deadline, date(2026, 6, 16))
        self.assertIn("vence en 15 días", activity.summary, "In the responsible's language (es_AR)")
        self._run(date(2026, 6, 9))  # 7 days: same activity updated
        self.assertEqual(len(policy.activity_ids), 1)
        self.assertIn("vence en 7 días", policy.activity_ids.summary)
        self.assertTrue(any("15" in (m.body or "") for m in policy.message_ids), "Each notice is logged in the chatter")

    # End of validity ----------------------------------------------------------

    def test_expired_notice_the_day_after_if_not_renewed(self):
        policy = self._policy(date(2026, 6, 1))
        self._run(TODAY)  # expires today
        self.assertIn("vence hoy", self._mails(policy).subject)
        self._run(date(2026, 6, 2))
        self.assertEqual(policy.state, "expired")
        expired = self._mails(policy).filtered(lambda m: "venció" in m.subject)
        self.assertEqual(len(expired), 1)
        self._run(date(2026, 6, 2), policies=policy)
        self.assertEqual(len(self._mails(policy).filtered(lambda m: "venció" in m.subject)), 1, "Only once")

    def test_not_renewed_policy_gets_expired_notice(self):
        policy = self._policy(date(2026, 6, 1))
        with freeze_time(TODAY):
            policy._mark_non_renewal("Sold")
        self._run(date(2026, 6, 2))
        self.assertEqual(policy.state, "not_renewed")
        self.assertTrue(self._mails(policy).filtered(lambda m: "venció" in m.subject))

    def test_renewed_policies_do_not_alert(self):
        policy = self._policy(date(2026, 6, 20))
        self._run(TODAY)
        sent = len(self._mails(policy))
        with freeze_time(TODAY):
            policy.action_renew()
        self._run(date(2026, 6, 13))  # 7 days: would notify if not renewed
        self.assertEqual(len(self._mails(policy)), sent)
        self._run(date(2026, 6, 21))
        self.assertEqual(policy.state, "renewed")
        self.assertEqual(len(self._mails(policy)), sent, "No 'expired' email either")

    def test_no_recipient_is_reported_in_the_chatter(self):
        self.responsible.email = False
        policy = self._policy(date(2026, 6, 16))
        self._run(TODAY)
        self.assertFalse(self._mails(policy))
        self.assertTrue(any("no user to notify has an email address" in (m.body or "") or "ningún usuario" in (m.body or "") for m in policy.message_ids))

    def test_draft_and_cancelled_policies_do_not_alert(self):
        with freeze_time(TODAY):
            draft = self._create_policy(policy_number="DRAFT", date_from=date(2025, 6, 10), date_to=date(2026, 6, 9))
        cancelled = self._policy(date(2026, 6, 9), policy_number="CANC")
        cancelled.with_context(insurance_lifecycle_write=True).write({"state": "cancelled"})
        self._run(TODAY)
        self.assertFalse(self._mails(draft) | self._mails(cancelled))
        self.assertEqual(cancelled.state, "cancelled")

    def test_error_on_one_policy_does_not_stop_the_others(self):
        bad = self._policy(date(2026, 6, 10), policy_number="BAD")
        good = self._policy(date(2026, 6, 10), policy_number="GOOD")
        original = InsurancePolicy._process_expiry_notice

        def failing(policy, today):
            if policy.policy_number == "BAD":
                raise ValueError("Simulated failure")
            return original(policy, today)

        with patch.object(InsurancePolicy, "_process_expiry_notice", failing), mute_logger(
            "odoo.addons.insurance_management.models.insurance_policy"
        ):
            failed = self._run(TODAY, policies=bad | good)
        self.assertEqual(failed, bad)
        self.assertTrue(self._mails(good))
        self.assertFalse(self._mails(bad))

    def test_cron_processes_all_policies_in_batches(self):
        policies = self._policy(date(2026, 6, 10), policy_number="B1") | self._policy(
            date(2026, 6, 12), policy_number="B2"
        ) | self._policy(date(2026, 6, 14), policy_number="B3")
        self.env["ir.config_parameter"].sudo().set_param("insurance_management.cron_batch_size", 2)
        calls = []
        with patch.object(type(self.env["ir.cron"]), "_commit_progress", lambda self, processed=0, **kw: calls.append(processed) or 1.0), freeze_time(TODAY):
            self.Policy._cron_process_expiry()
        self.assertTrue(calls and all(processed <= 2 for processed in calls), calls)
        self.assertEqual(sum(calls), self.Policy.search_count([("state", "in", ("in_force", "expiring"))]))
        for policy in policies:
            self.assertTrue(self._mails(policy))

    def test_cron_definition(self):
        cron = self.env.ref("insurance_management.ir_cron_insurance_policy_expiry")
        self.assertTrue(cron.active)
        self.assertEqual((cron.interval_number, cron.interval_type), (1, "days"))
        self.assertEqual(cron.nextcall.hour, 10, "07:00 in Argentina is 10:00 UTC")
        self.assertTrue(
            self.env["ir.model.data"].search(
                [("module", "=", "insurance_management"), ("name", "=", "ir_cron_insurance_policy_expiry")]
            ).noupdate
        )

    def test_expires_today_flag_and_filter(self):
        policy = self._policy(date(2026, 6, 1))
        with freeze_time(TODAY):
            policy.invalidate_recordset(["expires_today"])
            self.assertTrue(policy.expires_today)
            self.assertIn(policy, self.Policy.search([("expires_today", "=", True)]))
        with freeze_time(date(2026, 5, 31)):
            policy.invalidate_recordset(["expires_today"])
            self.assertFalse(policy.expires_today)

    # Automatic non-renewal instruction ------------------------------------------

    def test_automatic_non_renewal_instruction(self):
        policy = self._policy(date(2026, 7, 31), non_renewal_send_mode="automatic", non_renewal_days=20)
        with freeze_time(TODAY):
            wizard = self.env["insurance.policy.non.renewal"].create({"policy_id": policy.id, "reason": "Sold"})
            self.assertFalse(wizard.send_instruction, "Automatic mode: not sent from the wizard")
            wizard.action_confirm()
        self._run(date(2026, 7, 10))  # 21 days left
        self.assertFalse(policy.non_renewal_sent_date)
        self._run(date(2026, 7, 11))  # 20 days left
        self.assertTrue(policy.non_renewal_sent_date)
        comments = policy.message_ids.filtered(lambda m: m.message_type == "comment")
        self.assertEqual(len(comments), 1)
        self.assertIn(self.producer, comments.partner_ids)
        self._run(date(2026, 7, 12))
        self.assertEqual(len(policy.message_ids.filtered(lambda m: m.message_type == "comment")), 1, "Once")

    def test_manual_non_renewal_is_never_sent_automatically(self):
        policy = self._policy(date(2026, 6, 20), non_renewal_send_mode="manual")
        with freeze_time(TODAY):
            policy._mark_non_renewal("Sold")
        self._run(date(2026, 6, 19))
        self.assertFalse(policy.non_renewal_sent_date)
