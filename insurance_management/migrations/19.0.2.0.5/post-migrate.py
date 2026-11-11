"""Payments keep no insurance fields (the link lives on the installment), and
the bridge with account_payment_pro is new: install it when its dependencies
are installed (see install_bridge_modules)."""

from odoo import SUPERUSER_ID, api

from odoo.addons.insurance_management.models.insurance_tools import install_bridge_modules


def migrate(cr, version):
    if not version:
        return
    install_bridge_modules(api.Environment(cr, SUPERUSER_ID, {}))
