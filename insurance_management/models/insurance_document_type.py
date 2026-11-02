from odoo import fields, models


class InsuranceDocumentType(models.Model):
    """Kind of document attached to a policy (policy, certificate...)."""

    _name = "insurance.document.type"
    _description = "Insurance document type"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text(translate=True)
