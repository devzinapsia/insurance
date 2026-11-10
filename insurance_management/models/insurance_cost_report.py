from odoo import fields, models, tools

AMOUNTS_GROUP = "insurance_management.group_insurance_see_amounts"


class InsuranceCostReport(models.Model):
    """Billed insurance cost: the product lines of the posted bills and credit
    notes linked to a policy, net of taxes, in company currency and in the
    original currency (RF-14)."""

    _name = "insurance.cost.report"
    _description = "Insurance cost by branch and insurer"
    _auto = False
    _order = "date desc"

    date = fields.Date(string="Date", readonly=True)
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Bill",
        readonly=True,
        groups="account.group_account_invoice,account.group_account_readonly",
    )
    policy_id = fields.Many2one(comodel_name="insurance.policy", string="Policy", readonly=True)
    branch_id = fields.Many2one(comodel_name="insurance.branch", string="Branch", readonly=True)
    insurer_id = fields.Many2one(comodel_name="res.partner", string="Insurer", readonly=True)
    company_id = fields.Many2one(comodel_name="res.company", string="Company", readonly=True)
    company_currency_id = fields.Many2one(comodel_name="res.currency", string="Company currency", readonly=True)
    currency_id = fields.Many2one(comodel_name="res.currency", string="Currency", readonly=True)
    amount = fields.Monetary(
        string="Cost",
        currency_field="company_currency_id",
        readonly=True,
        groups=AMOUNTS_GROUP,
    )
    amount_currency = fields.Monetary(
        string="Cost in original currency",
        currency_field="currency_id",
        readonly=True,
        groups=AMOUNTS_GROUP,
    )

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT line.id AS id,
                       line.date AS date,
                       line.move_id AS move_id,
                       policy.id AS policy_id,
                       policy.branch_id AS branch_id,
                       policy.insurer_id AS insurer_id,
                       line.company_id AS company_id,
                       line.company_currency_id AS company_currency_id,
                       line.currency_id AS currency_id,
                       line.balance AS amount,
                       line.amount_currency AS amount_currency
                  FROM account_move_line line
                  JOIN account_move move ON move.id = line.move_id
                  JOIN insurance_policy policy ON policy.id = move.insurance_policy_id
                 WHERE move.state = 'posted'
                   AND move.move_type IN ('in_invoice', 'in_refund')
                   AND line.display_type = 'product'
                   AND NOT COALESCE(move.insurance_opening_debt, FALSE)
            )
            """
        )
