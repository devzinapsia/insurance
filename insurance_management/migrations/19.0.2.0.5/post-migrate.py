"""Payments keep no insurance fields (the link lives on the installment), and
the bridge with account_payment_pro is new.

Bridge modules added after the first install (auto_install) are only
installed automatically when one of their dependencies gets installed, never
on a plain update of this module: mark the ones whose dependencies are all
installed, so the update installs them in the same run.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Module = env["ir.module.module"]
    Module.update_list()
    bridges = Module.search(
        [
            ("state", "=", "uninstalled"),
            ("auto_install", "=", True),
            ("dependencies_id.name", "=", "insurance_management"),
        ]
    )
    for bridge in bridges:
        # Dependency state is "unknown" when the module is not available
        # (e.g. Enterprise ones on a Community database).
        if all(dep.state in ("installed", "to upgrade", "to install") for dep in bridge.dependencies_id):
            bridge.button_install()
