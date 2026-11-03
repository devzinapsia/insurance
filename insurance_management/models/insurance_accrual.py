import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import date_utils

_logger = logging.getLogger(__name__)


class InsuranceAccrualLine(models.Model):
    """One month of the accrual plan of a policy (module accrual, section
    8.1): the premium waiting in the prepaid account goes to expense.

    Lines are generated in equal monthly parts and stay editable until their
    journal entry is created (e.g. when the insurer bills pro rata).
    """

    _name = "insurance.accrual.line"
    _description = "Insurance accrual line"
    _order = "policy_id, date, id"
    _check_company_auto = True

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        index=True,
        ondelete="cascade",
    )
    endorsement_id = fields.Many2one(
        comodel_name="insurance.endorsement",
        string="Endorsement",
        index="btree_not_null",
        ondelete="set null",
    )
    source_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Source document",
        index="btree_not_null",
        ondelete="set null",
        help="Bill or credit note whose prepaid amount this line accrues.",
    )
    company_id = fields.Many2one(related="policy_id.company_id", store=True, index=True)
    company_currency_id = fields.Many2one(related="company_id.currency_id", string="Company currency")
    date = fields.Date(string="Period", required=True, index=True, help="Last day of the accrued month.")
    amount = fields.Monetary(
        string="Amount",
        currency_field="company_currency_id",
        required=True,
        groups="insurance_management.group_insurance_see_amounts",
        help="Amount in company currency (at the rate of the bill).",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Journal entry",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    state = fields.Selection(
        selection=[("draft", "To accrue"), ("posted", "Accrued")],
        string="Status",
        compute="_compute_state",
        store=True,
    )

    @api.depends("move_id.state")
    def _compute_state(self):
        for line in self:
            line.state = "posted" if line.move_id.state == "posted" else "draft"

    def write(self, vals):
        if {"amount", "date"}.intersection(vals) and self.filtered("move_id") and not self.env.context.get("insurance_accrual_system"):
            raise UserError(self.env._("Accrued lines (with a journal entry) can no longer be changed."))
        if "date" in vals and vals["date"]:
            vals["date"] = date_utils.end_of(fields.Date.to_date(vals["date"]), "month")
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted(self):
        if self.filtered("move_id"):
            raise UserError(self.env._("Accrued lines (with a journal entry) cannot be deleted."))

    # -------------------------------------------------------------------------
    # Monthly process
    # -------------------------------------------------------------------------

    @api.model
    def _get_entry_date(self, company, journal, date):
        """First date allowed by the lock dates (an entry of a closed period is
        posted on the first open day)."""
        lock_date = company._get_user_fiscal_lock_date(journal)
        if lock_date and date <= lock_date:
            return lock_date + relativedelta(days=1)
        return date

    def _post_policy_month(self):
        """Create and post the accrual entry of one policy and month (self =
        the lines of that policy and month)."""
        policy = self.policy_id
        company = policy.company_id
        # Run by a scheduled action (no user language): entries are written
        # in the company language.
        self = self.with_context(lang=company.partner_id.lang or self.env.lang)
        journal = company.insurance_accrual_journal_id
        if not journal:
            raise UserError(
                self.env._("Set the accrual journal in the insurance settings to post the monthly accrual.")
            )
        expense = policy._get_expense_account()
        prepaid = policy._get_prepaid_account()
        if not expense or not prepaid:
            raise UserError(
                self.env._(
                    "Policy %(policy)s: set the expense and prepaid insurance accounts (insurance "
                    "product, branch or settings) to post the accrual.",
                    policy=policy.display_name,
                )
            )
        amount = sum(self.sudo().mapped("amount"))
        period = self[0].date
        if company.currency_id.is_zero(amount):
            self.with_context(insurance_accrual_system=True).write({"move_id": False})
            return self.env["account.move"]
        label = self.env._("Insurance accrual %(policy)s %(period)s", policy=policy.policy_number or policy.name, period=period.strftime("%m/%Y"))
        analytic = policy._get_analytic_distribution() or False
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": company.id,
                "date": self._get_entry_date(company, journal, period),
                "ref": label,
                "insurance_policy_id": policy.id,
                "insurance_accrual_date": period,
                "line_ids": [
                    fields.Command.create(
                        {
                            "name": label,
                            "account_id": expense.id,
                            "debit": amount if amount > 0 else 0.0,
                            "credit": -amount if amount < 0 else 0.0,
                            "analytic_distribution": analytic,
                        }
                    ),
                    fields.Command.create(
                        {
                            "name": label,
                            "account_id": prepaid.id,
                            "debit": -amount if amount < 0 else 0.0,
                            "credit": amount if amount > 0 else 0.0,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        self.with_context(insurance_accrual_system=True).write({"move_id": move.id})
        return move

    @api.model
    def _process_accrual_batch(self, lines):
        """Post the given lines grouped by policy and month, each group in its
        own savepoint: an error (missing setup, lock date) never stops the
        others. Returns the lines that failed."""
        failed = self.browse()
        groups = {}
        for line in lines.filtered(lambda l: not l.move_id):
            groups.setdefault((line.policy_id, line.date), self.browse())
            groups[(line.policy_id, line.date)] |= line
        for (policy, _date), group in groups.items():
            try:
                with self.env.cr.savepoint():
                    group.with_company(policy.company_id)._post_policy_month()
            except Exception:
                _logger.exception("Insurance accrual failed for policy %s", policy.id)
                failed |= group
        return failed

    @api.model
    def _cron_post_accruals(self):
        today = fields.Date.context_today(self)
        batch_size = int(
            self.env["ir.config_parameter"].sudo().get_param("insurance_management.cron_batch_size", 200)
        ) or 200
        lines = self.sudo().search([("move_id", "=", False), ("date", "<=", today)], order="policy_id, date, id")
        policies = lines.policy_id
        remaining = len(policies)
        for start in range(0, len(policies), batch_size):
            batch_policies = policies[start:start + batch_size]
            self._process_accrual_batch(lines.filtered(lambda l: l.policy_id in batch_policies))
            remaining -= len(batch_policies)
            self.env["ir.cron"]._commit_progress(len(batch_policies), remaining=remaining)
