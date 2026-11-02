import base64
from datetime import date

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests import Form, new_test_user, tagged
from odoo.tools import convert_file

from .common import InsuranceCommon

PDF = base64.b64encode(b"%PDF-1.4 test document")


@tagged("post_install", "-at_install")
@freeze_time("2026-06-01")
class TestDocuments(InsuranceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.policy = cls._create_policy()
        cls.type_policy = cls.env.ref("insurance_management.insurance_document_type_policy")
        cls.type_certificate = cls.env.ref("insurance_management.insurance_document_type_certificate")

    def _upload(self, policy, user, doc_type, name="policy.pdf"):
        action = policy.with_user(user).action_open_document_upload()
        wizard = (
            self.env[action["res_model"]]
            .with_user(user)
            .with_context(action["context"])
            .create({"document_type_id": doc_type.id, "file": PDF, "filename": name})
        )
        wizard.action_upload()

    def test_initial_document_types(self):
        names = [
            "insurance_document_type_policy",
            "insurance_document_type_endorsement",
            "insurance_document_type_certificate",
            "insurance_document_type_payment_receipt",
            "insurance_document_type_invoice",
            "insurance_document_type_claim_report",
            "insurance_document_type_other",
        ]
        types = self.env["insurance.document.type"].browse(
            [self.env.ref(f"insurance_management.{name}").id for name in names]
        )
        self.assertEqual(len(types), 7)
        self.type_policy.name = "Signed policy"
        convert_file(
            self.env, "insurance_management", "data/insurance_document_type_data.xml",
            idref={}, mode="update", noupdate=False,
        )
        self.type_policy.invalidate_recordset()
        self.assertEqual(self.type_policy.name, "Signed policy", "Not overwritten on update")

    def test_upload_from_tab_requires_type(self):
        Upload = self.env["insurance.policy.document.upload"].with_context(default_policy_id=self.policy.id)
        form = Form(Upload.with_user(self.insurance_user))
        form.file = PDF
        with self.assertRaises(AssertionError, msg="Document type is required"):
            form.save()
        self._upload(self.policy, self.insurance_user, self.type_policy)
        attachment = self.policy.attachment_ids
        self.assertEqual(attachment.name, "policy.pdf")
        self.assertEqual(attachment.insurance_document_type_id, self.type_policy)
        self.assertEqual(attachment.raw, b"%PDF-1.4 test document")
        self.assertIn("policy.pdf", self.policy.message_ids[0].body)

    def test_chatter_attachments_are_counted(self):
        self._upload(self.policy, self.insurance_user, self.type_policy)
        # A file attached from the chatter: no document type.
        chatter_file = self.env["ir.attachment"].with_user(self.insurance_user).create(
            {"name": "photo.jpg", "datas": PDF, "res_model": "insurance.policy", "res_id": self.policy.id}
        )
        self.policy.message_post(body="See attached", attachment_ids=chatter_file.ids)
        self.policy.invalidate_recordset(["document_count", "attachment_ids"])
        self.assertEqual(self.policy.document_count, 2)
        self.assertIn(chatter_file, self.policy.attachment_ids)
        action = self.policy.action_view_documents()
        self.assertEqual(len(self.env["ir.attachment"].search(action["domain"])), 2)
        # Its type can be set later, from the policy form.
        self.policy.with_user(self.insurance_user).write(
            {"attachment_ids": [(1, chatter_file.id, {"insurance_document_type_id": self.type_certificate.id})]}
        )
        self.assertEqual(chatter_file.insurance_document_type_id, self.type_certificate)

    def test_documents_allowed_on_locked_policy(self):
        policy = self._create_policy(policy_number="OLD", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
        policy.action_confirm()
        self.assertTrue(policy.is_locked)
        self._upload(policy, self.insurance_user, self.type_certificate, "certificate.pdf")
        attachment = policy.attachment_ids
        policy.with_user(self.insurance_user).write(
            {"attachment_ids": [(1, attachment.id, {"insurance_document_type_id": self.type_policy.id})]}
        )
        self.assertEqual(attachment.insurance_document_type_id, self.type_policy)

    def test_document_types_managed_by_administrator(self):
        Type = self.env["insurance.document.type"]
        self.assertTrue(Type.with_user(self.insurance_user).search([]))
        with self.assertRaises(AccessError):
            Type.with_user(self.insurance_user).create({"name": "Not allowed"})
        doc_type = Type.with_user(self.insurance_manager).create({"name": "Inspection report"})
        doc_type.write({"active": False})

    def test_documents_follow_policy_company(self):
        company_b = self.env["res.company"].create({"name": "Insurance company B"})
        policy_b = self.env["insurance.policy"].with_company(company_b).create(
            self._policy_vals(company_id=company_b.id, branch_id=self.branch_fire.id)
        )
        user_b = new_test_user(
            self.env, login="docs_b",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=company_b.id, company_ids=[company_b.id],
        )
        self._upload(policy_b, user_b, self.type_policy, "b.pdf")
        with self.assertRaises(AccessError):
            policy_b.attachment_ids.with_user(self.insurance_user).read(["name"])
