from random import randint

from odoo import fields, models


class InsurancePolicyTag(models.Model):
    _name = "insurance.policy.tag"
    _description = "Insurance policy tag"
    _order = "name"

    name = fields.Char(required=True)
    color = fields.Integer(default=lambda self: randint(1, 11))

    _name_uniq = models.Constraint("UNIQUE (name)", "A tag with this name already exists.")
