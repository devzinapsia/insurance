from datetime import date

from odoo.tests import TransactionCase, new_test_user


class InsuranceCommon(TransactionCase):
    """Shared fixtures: a branch, an insurer, a producer and two users."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "insurance_min_duration_months": 1,
                "insurance_max_duration_months": 12,
                "insurance_duration_check": "block",
            }
        )
        cls.branch = cls.env.ref("insurance_management.insurance_branch_motor")
        cls.branch_fire = cls.env.ref("insurance_management.insurance_branch_fire")
        Partner = cls.env["res.partner"]
        cls.insurer = Partner.create({"name": "Insurer SA", "is_company": True, "is_insurer": True})
        cls.insurer_2 = Partner.create({"name": "Other insurer SA", "is_company": True, "is_insurer": True})
        cls.producer = Partner.create({"name": "Producer", "is_insurance_producer": True})
        cls.insurance_user = new_test_user(
            cls.env,
            login="ins_user",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.insurance_manager = new_test_user(
            cls.env,
            login="ins_manager",
            groups="base.group_user,insurance_management.group_insurance_manager",
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )

    @classmethod
    def _policy_vals(cls, **values):
        vals = {
            "policy_number": "POL-001",
            "branch_id": cls.branch.id,
            "insurer_id": cls.insurer.id,
            "producer_id": cls.producer.id,
            "date_from": date(2026, 1, 1),
            "date_to": date(2026, 12, 31),
            "premium": 1000.0,
            "premium_total": 1210.0,
        }
        vals.update(values)
        return vals

    @classmethod
    def _create_policy(cls, user=None, **values):
        env = cls.env(user=user) if user else cls.env
        return env["insurance.policy"].create(cls._policy_vals(**values))
