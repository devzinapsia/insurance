import base64
from datetime import date

from odoo import Command
from odoo.tests import new_test_user, tagged

from odoo.addons.insurance_management.tests.common_accounting import InsuranceAccountingCommon

from ..hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestInsuranceDocuments(InsuranceAccountingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env.ref("insurance_management_documents.documents_insurance_folder")
        cls.company.insurance_documents_settings = True
        cls.company.insurance_documents_folder_id = cls.folder
        cls.doc_type = cls.env.ref("insurance_management.insurance_document_type_policy")

    def _upload(self, record, user=None):
        wizard = self.env["insurance.policy.document.upload"].with_user(user or self.env.user).create(
            {
                ("claim_id" if record._name == "insurance.claim" else "policy_id"): record.id,
                "document_type_id": self.doc_type.id,
                "file": base64.b64encode(b"pdf"),
                "filename": "file.txt",
            }
        )
        wizard.action_upload()
        return self.env["ir.attachment"].search([("res_model", "=", record._name), ("res_id", "=", record.id)], order="id desc", limit=1)

    def _document(self, attachment):
        return self.env["documents.document"].sudo().search([("attachment_id", "=", attachment.id)])

    def test_policy_and_claim_files_go_to_the_insurance_folder(self):
        policy = self._policy(object_ids=[Command.create({"name": "Truck"})])
        attachment = self._upload(policy)
        document = self._document(attachment)
        self.assertEqual(document.folder_id, self.folder)
        self.assertEqual(document.res_model, "insurance.policy")
        self.assertEqual(document.res_id, policy.id)
        self.assertEqual(document.partner_id, self.insurer)
        self.assertIn(self.env.ref("insurance_management_documents.documents_tag_insurance_policy"), document.tag_ids)
        # The policy keeps showing its documents.
        self.assertEqual(policy.document_count, 1)
        self.assertIn(attachment, policy.attachment_ids)
        claim = self.env["insurance.claim"].create({"policy_id": policy.id, "date_occurred": date(self.year, 3, 1)})
        claim_document = self._document(self._upload(claim))
        self.assertEqual(claim_document.folder_id, self.folder)
        self.assertIn(self.env.ref("insurance_management_documents.documents_tag_insurance_claim"), claim_document.tag_ids)

    def test_disabled_setting_creates_no_document(self):
        self.company.insurance_documents_settings = False
        policy = self._policy()
        self.assertFalse(self._document(self._upload(policy)))

    def test_insurance_user_without_documents_rights_uploads(self):
        user = new_test_user(
            self.env, login="ins_nodocs",
            groups="base.group_user,insurance_management.group_insurance_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        policy = self._policy()
        attachment = self._upload(policy, user=user)
        self.assertTrue(self._document(attachment))
        self.assertEqual(policy.with_user(user).document_count, 1)

    def test_folder_members_see_the_documents(self):
        """The folder is restricted: a Documents user sees the insurance
        files only once the folder is shared with them."""
        member = new_test_user(
            self.env, login="docs_member",
            groups="base.group_user,documents.group_documents_user",
            company_id=self.company.id, company_ids=[self.company.id],
        )
        policy = self._policy()
        document = self._document(self._upload(policy))
        Document = self.env["documents.document"].with_user(member)
        self.assertFalse(Document.search([("id", "=", document.id)]))
        self.folder.sudo().action_update_access_rights(partners={member.partner_id: ("view", False)})
        document.invalidate_recordset()
        self.assertEqual(Document.search([("id", "=", document.id)]), document)
        new_document = self._document(self._upload(policy))
        self.assertEqual(Document.search([("id", "=", new_document.id)]), new_document)

    def test_install_hook_documents_existing_files(self):
        policy = self._policy()
        attachment = self.env["ir.attachment"].with_context(no_document=True).create(
            {"name": "old.txt", "datas": base64.b64encode(b"old"), "res_model": "insurance.policy", "res_id": policy.id}
        )
        self.assertFalse(self._document(attachment))
        post_init_hook(self.env)
        self.assertEqual(self._document(attachment).folder_id, self.folder)
        post_init_hook(self.env)
        self.assertEqual(len(self._document(attachment)), 1)

    def test_install_hook_silent_on_unreadable_pdf(self):
        """An encrypted or malformed PDF must not log a traceback while the
        existing files are documented (odoo.sh fails the build on it)."""
        policy = self._policy()
        attachment = self.env["ir.attachment"].with_context(no_document=True).create(
            {
                "name": "Encrypted policy.pdf",
                "datas": base64.b64encode(b"%PDF-1.4\nnot a readable pdf"),
                "mimetype": "application/pdf",
                "res_model": "insurance.policy",
                "res_id": policy.id,
            }
        )
        with self.assertNoLogs("odoo.addons.documents", level="WARNING"):
            post_init_hook(self.env)
            # The page count is a stored compute: it runs on flush.
            self.env.flush_all()
        document = self._document(attachment)
        self.assertEqual(document.folder_id, self.folder)
        self.assertFalse(document.is_multipage)
