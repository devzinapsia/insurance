from odoo import fields, models

from ..models.insurance_policy import DEFERRED


class InsuranceSettings(models.TransientModel):
    _inherit = "insurance.settings"

    accrual_method = fields.Selection(selection_add=DEFERRED, ondelete={"deferred": "set null"})
