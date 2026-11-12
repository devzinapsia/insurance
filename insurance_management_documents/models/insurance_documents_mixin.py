from odoo import models


class InsuranceDocumentsMixin(models.AbstractModel):
    """Shared behaviour of the insurance records whose attachments become
    documents of the Documents app (policies and claims)."""

    _name = "insurance.documents.mixin"
    _inherit = ["documents.mixin"]
    _description = "Insurance documents"

    _insurance_documents_tag = None

    def _get_document_folder(self):
        company = self.company_id or self.env.company
        if not company.insurance_documents_settings:
            return self.env["documents.document"]
        return company.insurance_documents_folder_id

    def _check_create_documents(self):
        company = self.company_id or self.env.company
        return company.insurance_documents_settings and super()._check_create_documents()

    def _get_document_partner(self):
        return self.insurer_id.commercial_partner_id

    def _get_document_tags(self):
        tag = self.env.ref(self._insurance_documents_tag, raise_if_not_found=False) if self._insurance_documents_tag else None
        return tag or self.env["documents.tag"]


class InsurancePolicy(models.Model):
    _name = "insurance.policy"
    _inherit = ["insurance.policy", "insurance.documents.mixin"]

    _insurance_documents_tag = "insurance_management_documents.documents_tag_insurance_policy"


class InsuranceClaim(models.Model):
    _name = "insurance.claim"
    _inherit = ["insurance.claim", "insurance.documents.mixin"]

    _insurance_documents_tag = "insurance_management_documents.documents_tag_insurance_claim"
