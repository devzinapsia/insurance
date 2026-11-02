from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    insurance_document_type_id = fields.Many2one(
        comodel_name="insurance.document.type",
        string="Document type",
        index="btree_not_null",
        ondelete="restrict",
        help="Kind of insurance document. Documents uploaded from the policy "
        "Documents tab always have one; files attached from the chatter can "
        "get it later.",
    )
