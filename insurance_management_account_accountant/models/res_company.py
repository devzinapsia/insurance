from odoo import fields, models

from .insurance_policy import DEFERRED, _fallback_to_direct_expense


class ResCompany(models.Model):
    _inherit = "res.company"

    insurance_accrual_method = fields.Selection(
        selection_add=DEFERRED,
        ondelete={"deferred": _fallback_to_direct_expense("insurance_accrual_method")},
    )
