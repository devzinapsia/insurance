from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import date_utils

from .insurance_claim import OPEN_STATES as CLAIM_OPEN_STATES
from .insurance_policy import ACTIVE_STATES, AMOUNTS_GROUP, SURETY_OPEN_STATES


class InsuranceDashboard(models.TransientModel):
    """Insurance dashboard (section 7): what needs attention today, each
    figure opening the records behind it. Computed on every read, for the
    companies selected in the company switcher."""

    _name = "insurance.dashboard"
    _description = "Insurance dashboard"

    company_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    expiring_30_count = fields.Integer(string="Expire in 30 days", compute="_compute_policies")
    expiring_60_count = fields.Integer(string="Expire in 60 days", compute="_compute_policies")
    expiring_90_count = fields.Integer(string="Expire in 90 days", compute="_compute_policies")
    expired_count = fields.Integer(string="Expired without renewal", compute="_compute_policies")
    in_force_count = fields.Integer(string="Policies in force", compute="_compute_policies")
    with_debt_count = fields.Integer(string="Policies with unpaid installments", compute="_compute_policies")
    installments_month_count = fields.Integer(string="Installments due this month", compute="_compute_installments")
    installments_month_pending = fields.Monetary(
        string="To pay this month",
        currency_field="company_currency_id",
        compute="_compute_installments",
        groups=AMOUNTS_GROUP,
    )
    installments_month_paid = fields.Monetary(
        string="Paid this month",
        currency_field="company_currency_id",
        compute="_compute_installments",
        groups=AMOUNTS_GROUP,
    )
    overdue_installment_count = fields.Integer(string="Overdue unpaid installments", compute="_compute_installments")
    cost_year_amount = fields.Monetary(
        string="Insurance cost this year",
        currency_field="company_currency_id",
        compute="_compute_cost",
        groups=AMOUNTS_GROUP,
    )
    open_claim_count = fields.Integer(string="Open claims", compute="_compute_claims")
    stale_claim_count = fields.Integer(string="Claims without movement", compute="_compute_claims")
    claims_to_collect = fields.Monetary(
        string="Claims to collect",
        currency_field="company_currency_id",
        compute="_compute_claims",
        groups=AMOUNTS_GROUP,
    )
    open_surety_count = fields.Integer(string="Open surety bonds", compute="_compute_sureties")
    surety_to_release_count = fields.Integer(string="Sureties to release in 30 days", compute="_compute_sureties")
    surety_guaranteed_amount = fields.Monetary(
        string="Guaranteed amount",
        currency_field="company_currency_id",
        compute="_compute_sureties",
        groups=AMOUNTS_GROUP,
    )

    # -------------------------------------------------------------------------
    # Domains (shared by the figures and the buttons that open them)
    # -------------------------------------------------------------------------

    def _today(self):
        return self.env["insurance.policy"]._get_today()

    def _get_domains(self):
        today = self._today()
        month_start = date_utils.start_of(today, "month")
        month_end = date_utils.end_of(today, "month")
        domains = {
            "in_force": ("insurance.policy", [("state", "in", ACTIVE_STATES)]),
            "expired": ("insurance.policy", [("state", "=", "expired")]),
            "with_debt": ("insurance.policy", [("has_debt", "=", True)]),
            "installments_month": (
                "insurance.installment",
                [("due_date", ">=", month_start), ("due_date", "<=", month_end), ("state", "!=", "cancelled")],
            ),
            "overdue_installments": ("insurance.installment", [("state", "=", "overdue")]),
            "open_claims": ("insurance.claim", [("state", "in", CLAIM_OPEN_STATES)]),
            "stale_claims": ("insurance.claim", [("is_stale", "=", True)]),
            "claims_to_collect": (
                "insurance.claim",
                [("state", "=", "approved"), ("claim_type", "!=", "surety_execution"), ("claim_line_id", "!=", False)],
            ),
            "open_sureties": (
                "insurance.policy",
                [
                    ("is_surety", "=", True),
                    ("renewed_by_id", "=", False),
                    ("state", "not in", ("draft", "cancelled")),
                    ("surety_state", "in", SURETY_OPEN_STATES),
                ],
            ),
        }
        domains["sureties_to_release"] = (
            "insurance.policy",
            domains["open_sureties"][1] + [("surety_obligation_end", "<=", today + relativedelta(days=30))],
        )
        for days in (30, 60, 90):
            domains[f"expiring_{days}"] = (
                "insurance.policy",
                [
                    ("state", "in", ACTIVE_STATES),
                    ("date_to", ">=", today),
                    ("date_to", "<=", today + relativedelta(days=days)),
                ],
            )
        return domains

    def _count(self, key):
        model, domain = self._get_domains()[key]
        return self.env[model].search_count(domain)

    def _to_company_currency(self, amount, currency):
        company = self.env.company
        if not currency or currency == company.currency_id:
            return amount
        return currency._convert(amount, company.currency_id, company, self._today())

    # -------------------------------------------------------------------------
    # Compute methods
    # -------------------------------------------------------------------------

    @api.depends_context("allowed_company_ids", "insurance_today")
    def _compute_policies(self):
        for dashboard in self:
            dashboard.expiring_30_count = dashboard._count("expiring_30")
            dashboard.expiring_60_count = dashboard._count("expiring_60")
            dashboard.expiring_90_count = dashboard._count("expiring_90")
            dashboard.expired_count = dashboard._count("expired")
            dashboard.in_force_count = dashboard._count("in_force")
            dashboard.with_debt_count = dashboard._count("with_debt")

    @api.depends_context("allowed_company_ids", "insurance_today")
    def _compute_installments(self):
        for dashboard in self:
            model, domain = dashboard._get_domains()["installments_month"]
            installments = self.env[model].search(domain).sudo()
            dashboard.installments_month_count = len(installments)
            dashboard.installments_month_pending = sum(
                dashboard._to_company_currency(i.amount_residual, i.currency_id)
                for i in installments.filtered(lambda i: i.state != "paid")
            )
            dashboard.installments_month_paid = sum(
                dashboard._to_company_currency(i.amount, i.currency_id)
                for i in installments.filtered(lambda i: i.state == "paid")
            )
            dashboard.overdue_installment_count = dashboard._count("overdue_installments")

    @api.depends_context("allowed_company_ids", "insurance_today")
    def _compute_cost(self):
        for dashboard in self:
            today = dashboard._today()
            groups = self.env["insurance.cost.report"].sudo()._read_group(
                [
                    ("company_id", "in", self.env.companies.ids),
                    ("date", ">=", date_utils.start_of(today, "year")),
                    ("date", "<=", date_utils.end_of(today, "year")),
                ],
                aggregates=["amount:sum"],
            )
            dashboard.cost_year_amount = groups[0][0] if groups else 0.0

    @api.depends_context("allowed_company_ids", "insurance_today")
    def _compute_claims(self):
        for dashboard in self:
            dashboard.open_claim_count = dashboard._count("open_claims")
            dashboard.stale_claim_count = dashboard._count("stale_claims")
            model, domain = dashboard._get_domains()["claims_to_collect"]
            dashboard.claims_to_collect = sum(
                claim.claim_line_id.amount_residual for claim in self.env[model].search(domain).sudo()
            )

    @api.depends_context("allowed_company_ids", "insurance_today")
    def _compute_sureties(self):
        for dashboard in self:
            model, domain = dashboard._get_domains()["open_sureties"]
            sureties = self.env[model].search(domain).sudo()
            dashboard.open_surety_count = len(sureties)
            dashboard.surety_to_release_count = dashboard._count("sureties_to_release")
            dashboard.surety_guaranteed_amount = sum(
                dashboard._to_company_currency(p.surety_amount, p.currency_id) for p in sureties
            )

    @api.depends("company_currency_id")
    def _compute_display_name(self):
        for dashboard in self:
            dashboard.display_name = self.env._("Insurance dashboard")

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Dashboard"),
            "res_model": self._name,
            "res_id": dashboard.id,
            "view_mode": "form",
            "views": [(self.env.ref("insurance_management.insurance_dashboard_view_form").id, "form")],
            "target": "current",
        }

    def action_refresh(self):
        return self.action_open_dashboard()

    def _get_open_actions(self):
        """xmlid of the window action each figure opens (bridge modules add
        their own figures)."""
        return {
            "insurance.policy": "insurance_management.insurance_policy_action",
            "insurance.installment": "insurance_management.insurance_installment_action",
            "insurance.claim": "insurance_management.insurance_claim_action",
        }

    def action_open(self):
        """Open the records behind the figure named in the ``dashboard_key``
        context key."""
        self.ensure_one()
        key = self.env.context.get("dashboard_key")
        domains = self._get_domains()
        model, domain = domains[key]
        action = self.env["ir.actions.act_window"]._for_xml_id(self._get_open_actions()[model])
        action["domain"] = domain
        action["context"] = {}
        if model == "insurance.policy":
            action["view_mode"] = "list,kanban,form"
            action["views"] = [(False, "list"), (False, "kanban"), (False, "form")]
        if model == "insurance.claim":
            action["view_mode"] = "list,kanban,form"
            action["views"] = [(False, "list"), (False, "kanban"), (False, "form")]
        return action

    def action_open_cost(self):
        return self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_cost_report_action")
