from odoo.tools import mute_logger

INSURANCE_MODELS = ("insurance.policy", "insurance.claim")
# Documents logs a warning with a traceback for every PDF it cannot read
# (encrypted, malformed) while counting its pages, and odoo.sh fails the
# build on a traceback logged during an update. The document is still
# created, counted as a single page, as Documents does on any reading error.
DOCUMENTS_LOGGER = "odoo.addons.documents.models.documents_document"


def post_init_hook(env):
    """Default folder for every company, and a document for the policy and
    claim files attached before the module was installed."""
    folder = env.ref("insurance_management_documents.documents_insurance_folder", raise_if_not_found=False)
    if folder:
        env["res.company"].search([("insurance_documents_folder_id", "=", False)]).insurance_documents_folder_id = folder
    Attachment = env["ir.attachment"].sudo()
    documented = env["documents.document"].sudo().with_context(active_test=False).search(
        [("attachment_id.res_model", "in", INSURANCE_MODELS)]
    ).attachment_id
    attachments = Attachment.search([("res_model", "in", INSURANCE_MODELS), ("res_field", "=", False)]) - documented
    with mute_logger(DOCUMENTS_LOGGER):
        for attachment in attachments:
            attachment._create_document({"res_model": attachment.res_model, "res_id": attachment.res_id})
        env.flush_all()
