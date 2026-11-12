from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    insurance_documents_settings = fields.Boolean(
        related="company_id.insurance_documents_settings",
        readonly=False,
        string="Centralize insurance documents",
    )
    insurance_documents_folder_id = fields.Many2one(
        comodel_name="documents.document",
        related="company_id.insurance_documents_folder_id",
        readonly=False,
        string="Insurance folder",
        domain=[("type", "=", "folder"), ("shortcut_document_id", "=", False)],
    )
