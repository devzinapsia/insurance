"""Fase 3: claims, surety bonds and the dashboard, with new bridges for Fleet,
Employees, Sales and Projects: install them when their dependencies are
installed (see install_bridge_modules)."""

from odoo import SUPERUSER_ID, api

from odoo.addons.insurance_management.models.insurance_tools import install_bridge_modules


def migrate(cr, version):
    if not version:
        return
    install_bridge_modules(api.Environment(cr, SUPERUSER_ID, {}))
