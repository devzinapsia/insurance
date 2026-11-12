INSURANCE_MODELS = ("insurance.policy", "insurance.claim")


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
    for attachment in attachments:
        attachment._create_document({"res_model": attachment.res_model, "res_id": attachment.res_id})
