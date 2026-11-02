from odoo import fields, models


class InsurancePolicyDocumentUpload(models.TransientModel):
    _name = "insurance.policy.document.upload"
    _description = "Upload a policy document"

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        readonly=True,
    )
    document_type_id = fields.Many2one(
        comodel_name="insurance.document.type",
        string="Document type",
        required=True,
    )
    file = fields.Binary(string="File", required=True)
    filename = fields.Char(string="File name")
    description = fields.Char(
        string="Description",
        help="Optional name of the document; the file name is used if empty.",
    )

    def action_upload(self):
        self.ensure_one()
        self.env["ir.attachment"].create(
            {
                "name": self.description or self.filename or self.document_type_id.name,
                "datas": self.file,
                "res_model": "insurance.policy",
                "res_id": self.policy_id.id,
                "insurance_document_type_id": self.document_type_id.id,
            }
        )
        self.policy_id._message_log(
            body=self.env._(
                "Document uploaded: %(name)s (%(type)s)",
                name=self.description or self.filename,
                type=self.document_type_id.name,
            )
        )
        return {"type": "ir.actions.act_window_close"}
