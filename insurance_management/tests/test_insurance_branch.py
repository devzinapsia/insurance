from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import convert_file, mute_logger


@tagged("post_install", "-at_install")
class TestInsuranceBranch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Branch = cls.env["insurance.branch"]
        cls.motor = cls.env.ref("insurance_management.insurance_branch_motor")
        cls.surety = cls.env.ref("insurance_management.insurance_branch_surety")

    def test_initial_branches_installed(self):
        """The ten branches of section 4.2 are installed with their data."""
        xmlids = [
            "insurance_branch_motor",
            "insurance_branch_surety",
            "insurance_branch_personal_accident",
            "insurance_branch_group_life",
            "insurance_branch_fire",
            "insurance_branch_commercial_comprehensive",
            "insurance_branch_theft",
            "insurance_branch_electronic_equipment",
            "insurance_branch_cargo",
            "insurance_branch_civil_liability",
        ]
        branches = self.Branch.browse(
            [self.env.ref(f"insurance_management.{xmlid}").id for xmlid in xmlids]
        )
        self.assertEqual(len(branches), 10)
        self.assertEqual(self.motor.object_type, "vehicle")
        self.assertEqual(self.motor.alert_days, "30")
        self.assertEqual(self.surety.object_type, "contract")
        self.assertEqual(self.surety.alert_days, "60")
        self.assertEqual(
            self.env.ref("insurance_management.insurance_branch_civil_liability").object_type,
            "generic",
        )
        self.assertFalse(any(branches.mapped("company_id")), "Initial branches are shared")

    def test_initial_branches_editable_and_not_overwritten(self):
        """Edited initial branches survive a module data update (noupdate)."""
        self.motor.write({"name": "Motor fleet", "alert_days": "45,10", "code": "FLOTA"})
        convert_file(
            self.env,
            "insurance_management",
            "data/insurance_branch_data.xml",
            idref={},
            mode="update",
            noupdate=False,
        )
        self.motor.invalidate_recordset()
        self.assertEqual(self.motor.name, "Motor fleet")
        self.assertEqual(self.motor.alert_days, "45,10")
        self.assertEqual(self.motor.code, "FLOTA")

    def test_initial_branches_translated(self):
        """Branch names are English source, translated to Spanish."""
        self.env["res.lang"]._activate_lang("es_AR")
        self.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        self.assertEqual(self.motor.with_context(lang="es_AR").name, "Automotor")
        self.assertEqual(self.surety.with_context(lang="es_AR").name, "Caución")

    def test_alert_days_normalized(self):
        branch = self.Branch.create({"name": "Test branch", "alert_days": " 7, 30,15 ,30"})
        self.assertEqual(branch.alert_days, "30,15,7")
        self.assertEqual(branch.get_alert_days_list(), [30, 15, 7])
        branch.write({"alert_days": "5"})
        self.assertEqual(branch.alert_days, "5")
        branch.write({"alert_days": ""})
        self.assertFalse(branch.alert_days)
        self.assertEqual(branch.get_alert_days_list(), [])

    def test_alert_days_invalid(self):
        for value in ("abc", "0", "-5", "30,x", "1.5"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.Branch.create({"name": "Invalid", "alert_days": value})

    def test_code_unique_per_company(self):
        company_b = self.env["res.company"].create({"name": "Insurance company B"})
        self.Branch.create({"name": "B motor", "code": "AUTO", "company_id": company_b.id})
        self.Branch.create({"name": "No code 1"})
        self.Branch.create({"name": "No code 2"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.Branch.create({"name": "Shared duplicate", "code": "AUTO"})
                self.env.flush_all()
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.Branch.create(
                    {"name": "B duplicate", "code": "AUTO", "company_id": company_b.id}
                )
                self.env.flush_all()
