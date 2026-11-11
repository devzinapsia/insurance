from . import models
from . import report
from . import wizard


def post_init_hook(env):
    """Users see amounts by default ("hide costs" off). Done once here, not in
    the group XML, so module updates never undo the setting."""
    user_group = env.ref("insurance_management.group_insurance_user")
    user_group._apply_group(env.ref("insurance_management.group_insurance_see_amounts"))


def uninstall_hook(env):
    """Empty the policy tables before Odoo removes the module data.

    Odoo deletes the module's own records (e.g. the initial branches) before
    dropping the tables; policies are user data that still reference those
    branches, so without this the removal hits foreign-key errors and has to
    retry. The tables are dropped right after, so nothing is lost that the
    uninstall would not remove anyway. Insured objects cascade with policies.

    The per-company reference sequences are created on the fly (no xmlid), so
    they are removed here too; otherwise a reinstall would keep numbering.
    The files attached to the module's records (policy documents, chatter
    attachments) are deleted as well.
    """
    # Files attached to the module's records would be left orphaned.
    env["ir.attachment"].sudo().search([("res_model", "=like", "insurance.%")]).unlink()
    # Claims reference policies (restrict) and are numbered by their own
    # per-company sequence, created on the fly.
    env.cr.execute("UPDATE account_move SET insurance_claim_id = NULL WHERE insurance_claim_id IS NOT NULL")
    env.cr.execute("DELETE FROM insurance_claim")
    env["ir.sequence"].sudo().search([("code", "=", "insurance.claim")]).unlink()
    env.cr.execute("DELETE FROM insurance_policy")
    env["ir.sequence"].sudo().search([("code", "=", "insurance.policy")]).unlink()
