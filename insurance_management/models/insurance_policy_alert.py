from odoo import fields, models


class InsurancePolicyAlert(models.Model):
    """Log of the alerts sent for a policy, one row per threshold.

    Rows are matched with the policy end date they were sent for, so moving
    the end date starts the alerts over while keeping the old rows as history.
    """

    _name = "insurance.policy.alert"
    _description = "Insurance policy alert"
    _order = "sent_on desc, id desc"

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="policy_id.company_id", store=True, index=True)
    alert_type = fields.Selection(
        selection=[
            ("expiry_notice", "Expiry notice"),
            ("expired", "Policy expired"),
            ("surety_release_request", "Surety release request"),
            ("surety_unreleased", "Surety ended with the guarantee open"),
        ],
        string="Alert",
        required=True,
    )
    threshold_days = fields.Integer(string="Threshold (days)")
    date_to = fields.Date(string="For end date", required=True)
    sent_on = fields.Date(string="Date", required=True)
    skipped = fields.Boolean(
        string="Covered by a later notice",
        help="Several thresholds were crossed at once: only the one closest to "
        "the end date was sent and this one was marked as covered.",
    )
    recipient_ids = fields.Many2many(
        comodel_name="res.users",
        relation="insurance_policy_alert_user_rel",
        column1="alert_id",
        column2="user_id",
        string="Recipients",
    )
