from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from .insurance_endorsement import ENDORSEMENT_CTX

# Fields whose changes on a confirmed policy are logged on the policy chatter
# with their old and new values (transitional rule until endorsements exist).
LOGGED_FIELDS = (
    "name",
    "insured_item_id",
    "license_plate",
    "chassis_number",
    "engine_number",
    "sum_insured",
    "coverage",
    "date_start",
    "date_end",
    "exclusion_reason",
    "state",
)


# Context key allowing to link the master record of objects of confirmed or
# ended policies (see _get_master_link_fields).
MASTER_LINK_CTX = "insurance_master_link"


class InsurancePolicyObject(models.Model):
    """Insured object line: each thing or person covered by a policy."""

    _name = "insurance.policy.object"
    _description = "Insured object"
    _order = "policy_id, sequence, id"
    _check_company_auto = True

    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Description", required=True)
    company_id = fields.Many2one(related="policy_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="policy_id.currency_id")
    object_type = fields.Selection(related="policy_id.branch_id.object_type")
    policy_state = fields.Selection(related="policy_id.state", string="Policy status")
    insured_item_id = fields.Many2one(
        comodel_name="insurance.insured.item",
        string="Insurable item",
        index=True,
        check_company=True,
        help="Master record of the insured item, which keeps its insurance "
        "history across policies and renewals.",
    )
    license_plate = fields.Char(string="License plate")
    chassis_number = fields.Char(string="Chassis number")
    engine_number = fields.Char(string="Engine number")
    sum_insured = fields.Monetary(
        string="Sum insured",
        currency_field="currency_id",
        groups="insurance_management.group_insurance_see_amounts",
    )
    coverage = fields.Char(string="Coverage", help="E.g. third party, all risks with deductible.")
    date_start = fields.Date(string="Added on")
    date_end = fields.Date(string="Removed on", readonly=True)
    exclusion_reason = fields.Char(string="Removal reason", readonly=True)
    endorsement_in_id = fields.Many2one(
        comodel_name="insurance.endorsement",
        string="Added by endorsement",
        readonly=True,
        index="btree_not_null",
        ondelete="set null",
    )
    endorsement_out_id = fields.Many2one(
        comodel_name="insurance.endorsement",
        string="Removed by endorsement",
        readonly=True,
        index="btree_not_null",
        ondelete="set null",
    )
    state = fields.Selection(
        selection=[("active", "Active"), ("excluded", "Removed")],
        string="Status",
        required=True,
        default="active",
        readonly=True,
        index=True,
    )

    claim_ids = fields.One2many(comodel_name="insurance.claim", inverse_name="object_id", string="Claims")
    claim_count = fields.Integer(string="Claim count", compute="_compute_claim_amounts")
    claims_amount = fields.Monetary(
        string="Sum consumed by claims",
        currency_field="currency_id",
        groups="insurance_management.group_insurance_see_amounts",
        compute="_compute_claim_amounts",
        help="Indemnities of the approved claims that reduce the sum insured "
        "of this object and were not rehabilitated yet.",
    )
    sum_available = fields.Monetary(
        string="Sum available",
        currency_field="currency_id",
        groups="insurance_management.group_insurance_see_amounts",
        compute="_compute_claim_amounts",
        help="Sum insured minus the indemnities that consumed it.",
    )

    @api.depends("sum_insured", "claim_ids.state", "claim_ids.amount_approved", "claim_ids.sum_rehabilitated")
    def _compute_claim_amounts(self):
        for record in self:
            claims = record.sudo().claim_ids
            consumed = claims.filtered(
                lambda c: c.policy_effect == "reduce_sum"
                and c.state in ("approved", "collected", "closed")
                and not c.sum_rehabilitated
            )
            record.claim_count = len(claims)
            record.claims_amount = sum(consumed.mapped("amount_approved"))
            record.sum_available = record.sudo().sum_insured - record.claims_amount

    def _prepare_renewal_vals(self):
        """Values of this object on the renewal draft of its policy (bridge
        modules add their own links, e.g. the fleet vehicle)."""
        self.ensure_one()
        record = self.sudo()
        return {
            "sequence": record.sequence,
            "name": record.name,
            "insured_item_id": record.insured_item_id.id,
            "license_plate": record.license_plate,
            "chassis_number": record.chassis_number,
            "engine_number": record.engine_number,
            "sum_insured": record.sum_insured,
            "coverage": record.coverage,
        }

    @api.onchange("insured_item_id")
    def _onchange_insured_item_id(self):
        """Propose the description and the sum insured of the chosen item,
        without replacing what was already typed."""
        for line in self.filtered("insured_item_id"):
            values = line.insured_item_id._get_object_values(line.currency_id)
            if not line.name:
                line.name = values["name"]
            if "sum_insured" in values and not line.sum_insured:
                line.sum_insured = values["sum_insured"]

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    def _check_policy_editable(self, policies):
        """Objects of a draft policy are edited freely. Once the policy is
        confirmed they only change through an endorsement (RF-06), which
        keeps their history."""
        if self.env.context.get(ENDORSEMENT_CTX):
            policies = policies.filtered("is_locked")
        else:
            policies = policies.filtered(lambda policy: policy.state != "draft")
        if policies:
            raise UserError(
                self.env._(
                    "The insured objects of policy %(policy)s can only be changed with an "
                    "endorsement.",
                    policy=policies[0].display_name,
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        policies = self.env["insurance.policy"].browse(
            [vals["policy_id"] for vals in vals_list if vals.get("policy_id")]
        )
        self._check_policy_editable(policies)
        for vals in vals_list:
            if not vals.get("date_start") and vals.get("policy_id"):
                policy = self.env["insurance.policy"].browse(vals["policy_id"])
                if policy.state != "draft":
                    vals["date_start"] = policy._get_today()
                else:
                    vals["date_start"] = policy.date_from
        records = super().create(vals_list)
        for record in records.filtered(lambda r: r.policy_id.state != "draft"):
            record.policy_id._message_log(
                body=Markup("%s <b>%s</b>")
                % (self.env._("Insured object added:"), record.name),
                tracking_value_ids=record._prepare_tracking_values(
                    dict.fromkeys(LOGGED_FIELDS, False), only_set=True
                ),
            )
        return records

    @api.model
    def _get_master_link_fields(self):
        """Links to the master record of the object (insurable item; bridge
        modules add the fleet vehicle or the employee). Linking the master
        does not change the insured contract, so it is allowed on confirmed
        and ended policies with the MASTER_LINK_CTX context key."""
        return {"insured_item_id"}

    def write(self, vals):
        if not (self.env.context.get(MASTER_LINK_CTX) and set(vals) <= self._get_master_link_fields()):
            self._check_policy_editable(self.policy_id)
        logged = [fname for fname in LOGGED_FIELDS if fname in vals]
        confirmed = self.filtered(lambda r: r.policy_id.state != "draft")
        old_values = {
            record.id: {fname: record.sudo()[fname] for fname in logged} for record in confirmed
        }
        res = super().write(vals)
        for record in confirmed:
            tracking = record._prepare_tracking_values(old_values[record.id])
            if tracking:
                record.policy_id._message_log(
                    body=Markup("%s <b>%s</b>")
                    % (self.env._("Insured object modified:"), record.name),
                    tracking_value_ids=tracking,
                )
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed_policy(self):
        if any(record.policy_id.state != "draft" for record in self):
            raise UserError(
                self.env._(
                    "Insured objects of a confirmed policy cannot be deleted; remove "
                    "them from the policy instead, so their history is kept."
                )
            )

    # -------------------------------------------------------------------------
    # Helpers and actions
    # -------------------------------------------------------------------------

    def _prepare_tracking_values(self, old_values, only_set=False):
        """Build ``mail.tracking.value`` commands for the changed fields.

        Tracking values keep a reference to this model's fields, so the
        chatter applies each field's access groups when showing them.
        """
        self.ensure_one()
        # Read as superuser: users who cannot see amounts may still add or
        # edit objects; the chatter hides the amount trackings from them.
        self = self.sudo()
        TrackingValue = self.env["mail.tracking.value"]
        fields_info = self.fields_get(list(old_values), attributes=("type", "currency_field", "selection", "string"))
        commands = []
        for fname, old_value in old_values.items():
            new_value = self[fname]
            if old_value == new_value or (only_set and not new_value):
                continue
            commands.append(
                (0, 0, TrackingValue._create_tracking_values(old_value, new_value, fname, fields_info[fname], self))
            )
        return commands

    def _exclude(self, date_end, reason):
        """Remove the objects from their policy, keeping them as history."""
        if any(record.state != "active" for record in self):
            raise UserError(self.env._("Only active insured objects can be removed."))
        for record in self:
            if record.date_start and date_end < record.date_start:
                raise UserError(
                    self.env._("The removal date cannot be before the date the object was added.")
                )
        self.write({"state": "excluded", "date_end": date_end, "exclusion_reason": reason})
