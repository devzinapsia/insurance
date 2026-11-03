import base64
import io
from datetime import date

import openpyxl

from odoo.tests import tagged

from odoo.addons.insurance_management.models.insurance_import import SHEETS

from .common_accounting import InsuranceAccountingCommon


@tagged("post_install", "-at_install")
class TestImport(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.insurance_go_live_date = date(cls.year, 4, 1)
        cls.insurer.vat = "30500010912"

    def _workbook(self, policies, objects=(), installments=()):
        workbook = openpyxl.Workbook()
        workbook.remove(workbook.active)
        data = {"policies": policies, "objects": objects, "installments": installments}
        for key, title, columns in SHEETS:
            sheet = workbook.create_sheet(str(title))
            sheet.append(list(columns))
            sheet.append([str(header) for header in columns.values()])
            for row in data[key]:
                sheet.append([row.get(column) for column in columns])
        output = io.BytesIO()
        workbook.save(output)
        return base64.b64encode(output.getvalue())

    def _policy_row(self, **values):
        row = {
            "policy_number": "IMP-1",
            "insurer": "30-50001091-2",
            "producer": "Producer",
            "branch": "fleet",
            "date_from": date(self.year, 1, 1),
            "date_to": f"31/12/{self.year}",
            "premium": 1200000,
            "premium_total": "1.200.000,00",
            "in_progress": "Sí",
            "continue_from": 4,
            "installment_count": 12,
            "first_due_date": date(self.year, 1, 10),
            "payment_mode": "Bank debit",
            "unaccrued_amount": 900000,
        }
        row.update(values)
        return row

    def _import(self, datas):
        record = self.env["insurance.import"].create({"name": "Go-live", "file": datas, "filename": "load.xlsx"})
        record.action_read_file()
        return record

    def test_template(self):
        action = self.env["insurance.import"].action_download_template()
        attachment = self.env["ir.attachment"].browse(int(action["url"].split("/")[3].split("?")[0]))
        workbook = openpyxl.load_workbook(io.BytesIO(base64.b64decode(attachment.datas)))
        self.assertEqual(len(workbook.worksheets), 3)
        self.assertEqual(workbook.worksheets[0]["A1"].value, "policy_number")
        self.assertEqual(workbook.worksheets[1]["D1"].value, "name")

    def test_import_running_policy(self):
        datas = self._workbook(
            [self._policy_row(), self._policy_row(policy_number="IMP-2", in_progress="no", continue_from=None, installment_count=2, unaccrued_amount=None)],
            objects=[
                {"policy_number": "IMP-1", "insurer": "30-50001091-2", "date_from": date(self.year, 1, 1), "name": "Truck", "license_plate": "AB123CD", "sum_insured": 5000000},
                {"policy_number": "IMP-1", "insurer": "30-50001091-2", "date_from": date(self.year, 1, 1), "name": "Van", "license_plate": "AC456EF"},
            ],
            installments=[
                {"policy_number": "IMP-2", "insurer": "30-50001091-2", "date_from": date(self.year, 1, 1), "number": 2, "amount": 700000},
                {"policy_number": "IMP-2", "insurer": "30-50001091-2", "date_from": date(self.year, 1, 1), "number": 1, "amount": 500000, "due_date": f"{self.year}-01-20"},
            ],
        )
        record = self._import(datas)
        self.assertEqual((record.line_count, record.state), (2, "ready"))
        self.assertEqual(record.line_ids[0].object_count, 2)
        record.action_process()
        self.assertEqual(record.line_ids.mapped("state"), ["done", "done"], record.line_ids.mapped("message"))
        self.assertEqual(record.state, "done")
        running = record.line_ids[0].policy_id
        self.assertEqual(running.insurer_id, self.insurer, "Insurer found by VAT")
        self.assertEqual(running.branch_id, self.branch, "Branch found ignoring case")
        self.assertIn(running.state, ("in_force", "expiring"), "Confirmed")
        self.assertEqual(running.premium_total, 1200000.0, "Spanish number format")
        self.assertEqual(running.object_ids.mapped("license_plate"), ["AB123CD", "AC456EF"])
        installments = running.installment_ids
        self.assertEqual(len(installments), 12)
        self.assertEqual(installments.filtered("historical").mapped("number"), [1, 2, 3])
        self.assertEqual(installments[0].due_date, date(self.year, 1, 10))
        self.assertEqual(installments.payment_mode_id, self.debit_mode)
        self.assertEqual(len(running.accrual_line_ids), 9, "Initial accrual from go-live")
        self.assertEqual(sum(running.accrual_line_ids.mapped("amount")), 900000.0)
        other = record.line_ids[1].policy_id
        self.assertFalse(other.in_progress)
        self.assertEqual(other.installment_ids.mapped("amount"), [500000.0, 700000.0], "Amounts of the Installments sheet")
        self.assertEqual(other.installment_ids[0].due_date, date(self.year, 1, 20))
        self.assertFalse(other.accrual_line_ids)
        # Importing the same file again never touches the policies.
        again = self._import(datas)
        again.action_process()
        self.assertEqual(again.line_ids.mapped("state"), ["skipped", "skipped"])
        self.assertEqual(again.line_ids.policy_id, record.line_ids.policy_id)

    def test_row_errors_do_not_stop_the_others(self):
        datas = self._workbook(
            [
                self._policy_row(branch="Unknown branch"),
                self._policy_row(policy_number="IMP-OK", in_progress="no", installment_count=0, unaccrued_amount=None),
                self._policy_row(policy_number="IMP-DATE", date_from="32/13/2026"),
                self._policy_row(policy_number="IMP-NOPROD", producer=None),
            ]
        )
        record = self._import(datas)
        record.action_process()
        self.assertEqual(record.line_ids.mapped("state"), ["error", "done", "error", "error"])
        self.assertRegex(record.line_ids[3].message.lower(), "producer|productor")
        self.assertIn("Unknown branch", record.line_ids[0].message)
        self.assertIn("32/13/2026", record.line_ids[2].message)
        self.assertEqual(record.error_count, 3)
        # Fixed file: read again, only the failed rows are replaced.
        record.file = self._workbook(
            [
                self._policy_row(),
                self._policy_row(policy_number="IMP-OK", in_progress="no", installment_count=0, unaccrued_amount=None),
                self._policy_row(policy_number="IMP-DATE", date_from=date(self.year, 1, 1), in_progress="no", installment_count=0, unaccrued_amount=None),
                self._policy_row(policy_number="IMP-NOPROD", in_progress="no", installment_count=0, unaccrued_amount=None),
            ]
        )
        done = record.line_ids.filtered(lambda l: l.state == "done")
        record.action_read_file()
        self.assertIn(done, record.line_ids, "Imported lines are kept")
        self.assertEqual(record.line_count, 4)
        # The scheduled action commits (not allowed in tests): run its batch.
        self.env["insurance.import.line"]._process_batch(record.line_ids.filtered(lambda l: l.state == "pending"))
        self.assertEqual(set(record.line_ids.mapped("state")), {"done"})

    def test_import_messages_in_creator_language(self):
        self.env["res.lang"]._activate_lang("es_AR")
        self.env.ref("base.module_insurance_management")._update_translations(["es_AR"])
        self.env.user.lang = "es_AR"
        record = self._import(self._workbook([self._policy_row(branch="Inexistente")]))
        # The scheduled action runs without the user's language.
        self.env["insurance.import.line"].with_context(lang="en_US")._process_batch(record.line_ids)
        self.assertIn("no encontrado", record.line_ids.message)

    def test_link_posted_opening_bill(self):
        policy = self._policy(in_progress=True)
        bill = self.init_invoice("in_invoice", partner=self.insurer, invoice_date=date(self.year, 3, 1), amounts=[300000.0], post=True)
        bill.insurance_policy_id = policy
        self.assertEqual(policy.invoice_count, 1)
        self.assertEqual(policy.amount_due, 300000.0, "Debt with the insurer at go-live")
        self.assertFalse(policy.accrual_line_ids)

    def test_opening_balance_control(self):
        policy = self._policy(in_progress=True, unaccrued_amount=900000.0)
        settings = self.env["insurance.settings"].with_company(self.company).create({})
        self.assertEqual(settings.opening_unaccrued_total, 900000.0)
        self.assertEqual(settings.opening_prepaid_balance, 0.0)
        self.assertEqual(settings.opening_difference, -900000.0)
        opening = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date(self.year, 3, 31),
                "journal_id": self.company_data["default_journal_misc"].id,
                "line_ids": [
                    (0, 0, {"account_id": self.prepaid.id, "debit": 900000.0}),
                    (0, 0, {"account_id": self.company_data["default_account_revenue"].id, "credit": 900000.0}),
                ],
            }
        )
        opening.action_post()
        settings = self.env["insurance.settings"].with_company(self.company).create({})
        self.assertEqual(settings.opening_prepaid_balance, 900000.0)
        self.assertEqual(settings.opening_difference, 0.0)
        self.assertTrue(policy.in_progress)
