from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

AMOUNTS_GROUP = "insurance_management.group_insurance_see_amounts"
# Context key allowing an endorsement to change a confirmed policy and its
# insured objects (the only way once Fase 2 retired the transitional rule).
ENDORSEMENT_CTX = "insurance_endorsement_write"
# Kinds of endorsement (section 4.4).
ENDORSEMENT_KINDS = [
    ("add_object", "Add object"),
    ("remove_object", "Remove object"),
    ("increase_sum", "Sum insured increase"),
    ("decrease_sum", "Sum insured reduction"),
    ("coverage_change", "Coverage change"),
    ("data_change", "Data change"),
    ("extension", "Validity extension"),
    ("cancellation", "Cancellation"),
]
# Kinds that need object lines, and the operation each line performs.
LINE_OPERATION_BY_KIND = {
    "add_object": "add",
    "remove_object": "remove",
    "increase_sum": "change",
    "decrease_sum": "change",
}


class InsuranceEndorsementType(models.Model):
    _name = "insurance.endorsement.type"
    _description = "Insurance endorsement type"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True, tracking=True)
    kind = fields.Selection(selection=ENDORSEMENT_KINDS, required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text(translate=True)


class InsuranceEndorsement(models.Model):
    """Change to a policy in force (section 4.4, RF-06): objects added,
    removed or changed, coverage or data changes, extension or cancellation,
    with a premium difference that is billed or refunded."""

    _name = "insurance.endorsement"
    _description = "Insurance endorsement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "effective_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Reference", readonly=True, copy=False, default="/")
    endorsement_number = fields.Char(
        string="Endorsement number",
        tracking=True,
        help="Number assigned by the insurer.",
    )
    policy_id = fields.Many2one(
        comodel_name="insurance.policy",
        string="Policy",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        domain="[('state', 'in', ('not_started', 'in_force', 'expiring'))]",
    )
    company_id = fields.Many2one(related="policy_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="policy_id.currency_id")
    object_type = fields.Selection(related="policy_id.object_type")
    type_id = fields.Many2one(
        comodel_name="insurance.endorsement.type",
        string="Type",
        required=True,
        tracking=True,
    )
    kind = fields.Selection(related="type_id.kind", store=True)
    state = fields.Selection(
        selection=[("draft", "Draft"), ("confirmed", "Confirmed"), ("cancelled", "Cancelled")],
        string="Status",
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        tracking=True,
    )
    issue_date = fields.Date(string="Issue date", default=fields.Date.context_today, tracking=True)
    effective_date = fields.Date(
        string="Effective date",
        required=True,
        tracking=True,
        help="Date from which the endorsement applies. It must be within the "
        "policy validity.",
    )
    line_ids = fields.One2many(
        comodel_name="insurance.endorsement.line",
        inverse_name="endorsement_id",
        string="Objects",
        copy=True,
    )
    premium_difference = fields.Monetary(
        string="Premium difference",
        currency_field="currency_id",
        tracking=True,
        groups=AMOUNTS_GROUP,
        help="Positive: additional premium to pay (bill and additional "
        "installments). Negative: refund (credit note).",
    )
    premium_direction = fields.Selection(
        selection=[("increase", "Additional premium"), ("decrease", "Refund"), ("none", "No premium change")],
        string="Premium change",
        compute="_compute_premium_direction",
        compute_sudo=True,
        help="Whether the endorsement adds premium or refunds it, visible "
        "without access to amounts (drives the billing buttons).",
    )
    refund_mode = fields.Selection(
        selection=[
            ("installments", "Deduct from the next pending installments"),
            ("insurer", "Refund by the insurer"),
        ],
        string="Refund",
        default="installments",
        required=True,
        help="Only for a negative premium difference: how the refund is applied.",
    )
    new_date_to = fields.Date(string="New end date", help="Validity extension: new end date of the policy.")
    new_coverage = fields.Html(string="New coverages", help="Coverage change: new coverages and clauses of the policy.")
    new_producer_id = fields.Many2one(
        comodel_name="res.partner",
        string="New producer",
        domain="[('is_insurance_producer', '=', True)]",
        help="Data change: new producer of the policy.",
    )
    description = fields.Text(string="Description")
    claim_id = fields.Many2one(
        comodel_name="insurance.claim",
        string="Claim",
        readonly=True,
        copy=False,
        index="btree_not_null",
        ondelete="set null",
        help="Claim whose effect on the policy this endorsement applies "
        "(total loss, sum rehabilitation, replacement, surety execution).",
    )

    _number_policy_uniq = models.UniqueIndex(
        "(policy_id, endorsement_number) WHERE endorsement_number IS NOT NULL",
        "This endorsement number already exists for the policy.",
    )

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records.filtered(lambda e: e.name == "/"):
            count = self.search_count([("policy_id", "=", record.policy_id.id), ("id", "<=", record.id)])
            record.name = f"{record.policy_id.name}/E{count:02d}"
        return records

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        if any(endorsement.state == "confirmed" for endorsement in self):
            raise UserError(self.env._("Confirmed endorsements cannot be deleted: they are part of the policy history."))

    @api.constrains("effective_date", "policy_id", "kind", "new_date_to")
    def _check_dates(self):
        for endorsement in self.filtered(lambda e: e.state == "draft" and e.effective_date):
            policy = endorsement.policy_id
            if policy.date_from and policy.date_to and not (
                policy.date_from <= endorsement.effective_date <= policy.date_to
            ):
                raise ValidationError(
                    self.env._(
                        "The effective date of endorsement %(endorsement)s must be within the "
                        "policy validity.",
                        endorsement=endorsement.display_name,
                    )
                )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _check_can_confirm(self):
        self.ensure_one()
        env = self.env
        if self.state != "draft":
            raise UserError(env._("Endorsement %(name)s is not a draft.", name=self.display_name))
        if self.policy_id.state not in ("not_started", "in_force", "expiring"):
            raise UserError(
                env._("Endorsements can only be confirmed on policies not started yet, in force or expiring.")
            )
        operation = LINE_OPERATION_BY_KIND.get(self.kind)
        if operation:
            if not self.line_ids:
                raise UserError(env._("Add the insured objects affected by the endorsement."))
            if any(line.operation != operation for line in self.line_ids):
                raise UserError(
                    env._("All the lines of this endorsement type must be of the same operation.")
                )
        if self.kind == "extension" and (not self.new_date_to or self.new_date_to <= self.policy_id.date_to):
            raise UserError(env._("An extension needs a new end date after the current one."))
        if self.kind == "coverage_change" and not self.new_coverage and not self.line_ids:
            raise UserError(env._("Set the new coverages or the objects whose coverage changes."))
        if self.kind == "data_change" and not (self.new_producer_id or self.description):
            raise UserError(env._("Describe the data change or set the new producer."))

    def action_confirm(self):
        """Apply the endorsement to the policy and its insured objects."""
        for endorsement in self:
            endorsement._check_can_confirm()
            endorsement._apply_to_policy()
            endorsement.state = "confirmed"
            if endorsement.claim_id:
                endorsement.claim_id._on_endorsement_confirmed(endorsement)
            endorsement.policy_id._message_log(
                body=Markup("%s <b>%s</b> (%s)")
                % (
                    self.env._("Endorsement confirmed:"),
                    endorsement.display_name,
                    endorsement.type_id.name,
                )
            )
        return True

    def _apply_to_policy(self):
        self.ensure_one()
        policy = self.policy_id.with_context(**{ENDORSEMENT_CTX: True})
        for line in self.line_ids:
            line.with_context(**{ENDORSEMENT_CTX: True})._apply()
        if self.kind == "extension":
            policy.with_context(insurance_skip_duration_check=True).write({"date_to": self.new_date_to})
        if self.kind == "coverage_change" and self.new_coverage:
            policy.write({"coverage": self.new_coverage})
        if self.kind == "data_change" and self.new_producer_id:
            policy.write({"producer_id": self.new_producer_id.id})
        if self.kind == "cancellation":
            policy.with_context(insurance_lifecycle_write=True).write({"state": "cancelled"})
            pending = policy.installment_ids.filtered(lambda i: not i.is_locked)
            pending.with_context(insurance_installment_system=True).write({"cancelled": True})
            policy._close_accrual_plan(self.effective_date)

    installment_ids = fields.One2many(
        comodel_name="insurance.installment",
        inverse_name="endorsement_id",
        string="Installments",
    )
    move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="insurance_endorsement_id",
        string="Bills and credit notes",
    )

    @api.depends("premium_difference")
    def _compute_premium_direction(self):
        for endorsement in self:
            difference = endorsement.premium_difference
            currency = endorsement.currency_id
            if not difference or (currency and currency.is_zero(difference)):
                endorsement.premium_direction = "none"
            else:
                endorsement.premium_direction = "increase" if difference > 0 else "decrease"

    def action_open_installment_generator(self):
        self.ensure_one()
        if self.state != "confirmed" or self.sudo().premium_difference <= 0:
            raise UserError(self.env._("Only confirmed endorsements with an additional premium have installments."))
        return self.policy_id.action_open_installment_generator(endorsement=self)

    def action_create_bill(self):
        """Positive premium difference: bill(s) of the endorsement
        installments; negative: credit note."""
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(self.env._("Confirm the endorsement first."))
        difference = self.sudo().premium_difference
        policy = self.policy_id
        if difference < 0:
            if self.move_ids.filtered(lambda m: m.move_type == "in_refund" and m.state != "cancel"):
                raise UserError(self.env._("The credit note of this endorsement already exists."))
            return policy._action_view_moves(policy._create_credit_note(self))
        installments = self.installment_ids.filtered(lambda i: not i.move_id and not i.cancelled)
        if not installments:
            raise UserError(self.env._("Generate the endorsement installments first."))
        moves = self.env["account.move"]
        if policy.billing_mode == "installment":
            for installment in installments:
                moves |= policy._create_bill(installment, endorsement=self)
        else:
            moves = policy._create_bill(installments, endorsement=self)
        return policy._action_view_moves(moves)

    def action_cancel(self):
        if any(endorsement.state != "draft" for endorsement in self):
            raise UserError(self.env._("Only draft endorsements can be cancelled."))
        self.state = "cancelled"
        return True


class InsuranceEndorsementLine(models.Model):
    _name = "insurance.endorsement.line"
    _description = "Insurance endorsement line"
    _order = "endorsement_id, sequence, id"

    endorsement_id = fields.Many2one(
        comodel_name="insurance.endorsement",
        string="Endorsement",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="endorsement_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="endorsement_id.currency_id")
    policy_id = fields.Many2one(related="endorsement_id.policy_id")
    operation = fields.Selection(
        selection=[("add", "Add"), ("remove", "Remove"), ("change", "Change")],
        required=True,
        default="add",
    )
    object_id = fields.Many2one(
        comodel_name="insurance.policy.object",
        string="Insured object",
        domain="[('policy_id', '=', policy_id), ('state', '=', 'active')]",
        help="Object removed or changed.",
    )
    name = fields.Char(string="Description")
    insured_item_id = fields.Many2one(comodel_name="insurance.insured.item", string="Insurable item")
    license_plate = fields.Char(string="License plate")
    chassis_number = fields.Char(string="Chassis number")
    engine_number = fields.Char(string="Engine number")
    coverage = fields.Char(string="Coverage")
    old_sum_insured = fields.Monetary(
        string="Previous sum insured",
        currency_field="currency_id",
        compute="_compute_old_sum_insured",
        store=True,
        readonly=True,
        groups=AMOUNTS_GROUP,
    )
    sum_insured = fields.Monetary(
        string="New sum insured",
        currency_field="currency_id",
        groups=AMOUNTS_GROUP,
    )
    reason = fields.Char(string="Removal reason")

    @api.onchange("insured_item_id")
    def _onchange_insured_item_id(self):
        """New objects: propose the description and the sum insured of the
        chosen item, without replacing what was already typed."""
        for line in self.filtered(lambda l: l.insured_item_id and l.operation == "add"):
            values = line.insured_item_id._get_object_values(line.currency_id)
            if not line.name:
                line.name = values["name"]
            if "sum_insured" in values and not line.sum_insured:
                line.sum_insured = values["sum_insured"]

    @api.depends("object_id")
    def _compute_old_sum_insured(self):
        for line in self:
            line.old_sum_insured = line.sudo().object_id.sum_insured

    @api.constrains("operation", "object_id", "name")
    def _check_line(self):
        for line in self:
            if line.operation in ("remove", "change") and not line.object_id:
                raise ValidationError(self.env._("Choose the insured object to remove or change."))
            if line.operation == "add" and not line.name:
                raise ValidationError(self.env._("Describe the insured object to add."))

    def _prepare_object_vals(self):
        """Values of the insured object an "add" line creates (bridge modules
        add their own links, e.g. the fleet vehicle)."""
        self.ensure_one()
        line = self.sudo()
        endorsement = line.endorsement_id
        return {
            "policy_id": endorsement.policy_id.id,
            "name": line.name,
            "insured_item_id": line.insured_item_id.id,
            "license_plate": line.license_plate,
            "chassis_number": line.chassis_number,
            "engine_number": line.engine_number,
            "coverage": line.coverage,
            "sum_insured": line.sum_insured,
            "date_start": endorsement.effective_date,
            "endorsement_in_id": endorsement.id,
        }

    def _apply(self):
        """Apply the line to the policy objects (history is never deleted)."""
        self.ensure_one()
        endorsement = self.endorsement_id
        Object = self.env["insurance.policy.object"]
        line = self.sudo()
        if line.object_id:
            # Snapshot the value before applying the change (the stored compute
            # may run lazily, after the object has already been changed).
            line.old_sum_insured = line.object_id.sum_insured
        if self.operation == "add":
            Object.sudo().create(line._prepare_object_vals())
        elif self.operation == "remove":
            line.object_id._exclude(
                endorsement.effective_date,
                line.reason or endorsement.type_id.name,
            )
            line.object_id.endorsement_out_id = endorsement
        else:
            values = {"sum_insured": line.sum_insured}
            if line.coverage:
                values["coverage"] = line.coverage
            line.object_id.write(values)
