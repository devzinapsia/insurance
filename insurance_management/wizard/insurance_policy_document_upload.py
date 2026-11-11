from odoo import fields, models
from odoo.exceptions import UserError


class InsurancePolicyDocumentUpload(models.TransientModel):
    _name = "insurance.policy.document.upload"
    _description = "Upload a policy document"

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        readonly=True,
    )
    claim_id = fields.Many2one(
        comodel_name="insurance.claim",
        string="Claim",
        readonly=True,
        help="Set when the document is uploaded to a claim instead of a policy.",
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
        record = self.claim_id or self.policy_id
        if not record:
            raise UserError(self.env._("Choose the policy or the claim of the document."))
        self.env["ir.attachment"].create(
            {
                "name": self.description or self.filename or self.document_type_id.name,
                "datas": self.file,
                "res_model": record._name,
                "res_id": record.id,
                "insurance_document_type_id": self.document_type_id.id,
            }
        )
        record._message_log(
            body=self.env._(
                "Document uploaded: %(name)s (%(type)s)",
                name=self.description or self.filename,
                type=self.document_type_id.name,
            )
        )
        return {"type": "ir.actions.act_window_close"}
