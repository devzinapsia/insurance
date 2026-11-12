from odoo import api, fields, models
from odoo.fields import Domain


class ResCompany(models.Model):
    _inherit = "res.company"

    insurance_documents_settings = fields.Boolean(
        string="Centralize insurance documents",
        default=True,
        help="The files attached to policies and claims also appear in the Documents app, in the insurance folder.",
    )
    insurance_documents_folder_id = fields.Many2one(
        comodel_name="documents.document",
        string="Insurance folder",
        compute="_compute_insurance_documents_folder_id",
        store=True,
        readonly=False,
        domain="[('type', '=', 'folder'), ('shortcut_document_id', '=', False), '|', ('company_id', '=', False), ('company_id', '=', id)]",
        help="Folder of the Documents app where the policy and claim files are centralized.",
    )

    @api.depends("insurance_documents_settings")
    def _compute_insurance_documents_folder_id(self):
        folder = self.env.ref("insurance_management_documents.documents_insurance_folder", raise_if_not_found=False)
        self._reset_default_documents_folder_id("insurance_documents_settings", "insurance_documents_folder_id", folder)

    def _get_used_folder_ids_domain(self, folder_ids):
        return super()._get_used_folder_ids_domain(folder_ids) | (
            Domain("insurance_documents_folder_id", "in", folder_ids) & Domain("insurance_documents_settings", "=", True)
        )
