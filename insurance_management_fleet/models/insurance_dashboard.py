from odoo import api, fields, models


class InsuranceDashboard(models.TransientModel):
    _inherit = "insurance.dashboard"

    uninsured_vehicle_count = fields.Integer(
        string="Vehicles without insurance in force", compute="_compute_uninsured_vehicles"
    )

    def _get_domains(self):
        domains = super()._get_domains()
        domains["uninsured_vehicles"] = ("fleet.vehicle", [("insured_today", "=", False)])
        return domains

    def _get_open_actions(self):
        actions = super()._get_open_actions()
        actions["fleet.vehicle"] = "fleet.fleet_vehicle_action"
        return actions

    @api.depends_context("allowed_company_ids", "insurance_today")
    def _compute_uninsured_vehicles(self):
        for dashboard in self:
            model, domain = dashboard._get_domains()["uninsured_vehicles"]
            dashboard.uninsured_vehicle_count = self.env[model].sudo().with_context(
                allowed_company_ids=self.env.companies.ids
            ).search_count(domain + [("company_id", "in", self.env.companies.ids + [False])])
