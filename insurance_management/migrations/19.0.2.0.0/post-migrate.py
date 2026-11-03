"""Fase 2 upgrade from phase 1.

* The phase 1 "remove insured object" wizard was replaced by endorsements.
  Odoo removes the model on update but keeps its table, which no uninstall
  would ever drop afterwards: drop it here.
* Bridge modules added in phase 2 (auto_install, e.g. Enterprise deferred
  expenses, own checks) are only installed automatically when one of their
  dependencies gets installed, never on a plain update of this module: mark
  the ones whose dependencies are all installed, so the update installs them
  in the same run.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS insurance_policy_object_exclude CASCADE")
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
        if all(dep.state in ("installed", "to upgrade", "to install") for dep in bridge.dependencies_id.depend_id):
            bridge.button_install()
