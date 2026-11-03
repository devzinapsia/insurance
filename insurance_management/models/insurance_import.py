import base64
import io
import json
import logging
from datetime import date, datetime

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

_logger = logging.getLogger(__name__)

# Columns of the template, by sheet: (technical key, header). Row 1 holds the
# technical keys (read by the import, whatever the language of the headers),
# row 2 the headers for people, data from row 3.
POLICY_COLUMNS = {
    "policy_number": _lt("Policy number"),
    "insurer": _lt("Insurer (VAT or name)"),
    "producer": _lt("Producer (VAT or name)"),
    "branch": _lt("Branch"),
    "date_from": _lt("Valid from"),
    "date_to": _lt("Valid to"),
    "currency": _lt("Currency (code)"),
    "premium": _lt("Premium (net)"),
    "premium_total": _lt("Total premium"),
    "responsible": _lt("Responsible (login)"),
    "renewal_type": _lt("Renewal (undefined/renew/no_renew)"),
    "in_progress": _lt("Running policy (yes/no)"),
    "continue_from": _lt("Continues from installment"),
    "installment_count": _lt("Number of installments"),
    "first_due_date": _lt("First due date"),
    "payment_mode": _lt("Payment mode"),
    "unaccrued_amount": _lt("Amount still to accrue at go-live (company currency)"),
    "note": _lt("Notes"),
}
OBJECT_COLUMNS = {
    "policy_number": _lt("Policy number"),
    "insurer": _lt("Insurer (VAT or name)"),
    "date_from": _lt("Valid from"),
    "name": _lt("Description"),
    "license_plate": _lt("License plate"),
    "chassis_number": _lt("Chassis number"),
    "engine_number": _lt("Engine number"),
    "sum_insured": _lt("Sum insured"),
    "coverage": _lt("Coverage"),
}
INSTALLMENT_COLUMNS = {
    "policy_number": _lt("Policy number"),
    "insurer": _lt("Insurer (VAT or name)"),
    "date_from": _lt("Valid from"),
    "number": _lt("Installment number"),
    "due_date": _lt("Due date"),
    "amount": _lt("Amount"),
}
SHEETS = [
    ("policies", _lt("Policies"), POLICY_COLUMNS),
    ("objects", _lt("Objects"), OBJECT_COLUMNS),
    ("installments", _lt("Installments"), INSTALLMENT_COLUMNS),
]
# Header of each technical key, used as the label of the row errors.
HEADERS = {}
for _sheet, _title, _columns in SHEETS:
    for _key, _header in _columns.items():
        HEADERS.setdefault(_key, _header)
YES = {"yes", "y", "si", "sí", "s", "true", "1", "x"}


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _date(value):
    """openpyxl returns datetimes for date cells; text dates are accepted as
    YYYY-MM-DD or DD/MM/YYYY."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(text)


def _number(value):
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value).replace(" ", "")
    if "," in text and "." in text:
        # 1.234,56 (Spanish) or 1,234.56 (English)
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


class InsuranceImport(models.Model):
    """Bulk load of running policies at go-live (RF-11) from an Excel file:
    policies, their insured objects and, optionally, installment amounts.

    The file is read into one line per policy; lines are processed in batches
    (button or scheduled action), each in its own savepoint, with the same
    logic as a manual load: policy, objects, confirmation, installments and
    initial accrual. Already imported policies are never touched again.
    """

    _name = "insurance.import"
    _description = "Insurance import"
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(string="Description", required=True, default=lambda self: self.env._("Policy import"))
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    file = fields.Binary(string="Excel file", attachment=True)
    filename = fields.Char(string="File name")
    confirm_policies = fields.Boolean(
        string="Confirm policies",
        default=True,
        help="Confirm the imported policies (in force, expiring or expired "
        "according to their dates). Otherwise they stay as drafts.",
    )
    line_ids = fields.One2many(comodel_name="insurance.import.line", inverse_name="import_id", string="Policies")
    line_count = fields.Integer(string="Policies to import", compute="_compute_counts")
    pending_count = fields.Integer(string="Pending", compute="_compute_counts")
    done_count = fields.Integer(string="Imported", compute="_compute_counts")
    error_count = fields.Integer(string="With errors", compute="_compute_counts")
    skipped_count = fields.Integer(string="Already imported", compute="_compute_counts")
    state = fields.Selection(
        selection=[("draft", "To read"), ("ready", "To process"), ("done", "Done")],
        string="Status",
        compute="_compute_state",
        store=True,
    )

    @api.depends("line_ids.state")
    def _compute_counts(self):
        for record in self:
            states = record.line_ids.mapped("state")
            record.line_count = len(states)
            record.pending_count = states.count("pending")
            record.done_count = states.count("done")
            record.error_count = states.count("error")
            record.skipped_count = states.count("skipped")

    @api.depends("line_ids.state")
    def _compute_state(self):
        for record in self:
            states = set(record.line_ids.mapped("state"))
            if not states:
                record.state = "draft"
            elif states & {"pending", "error"}:
                record.state = "ready"
            else:
                record.state = "done"

    # -------------------------------------------------------------------------
    # Template
    # -------------------------------------------------------------------------

    def action_download_template(self):
        """Excel template: one sheet per kind of data, technical keys on the
        first (hidden) row and translated headers on the second."""
        import xlsxwriter  # noqa: PLC0415 (only needed here)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        bold = workbook.add_format({"bold": True, "bg_color": "#E8E8E8"})
        date_format = workbook.add_format({"num_format": "dd/mm/yyyy"})
        for _key, title, columns in SHEETS:
            sheet = workbook.add_worksheet(self.env._(title))
            for col, (key, header) in enumerate(columns.items()):
                sheet.write(0, col, key)
                sheet.write(1, col, self.env._(header), bold)
                width = max(len(self.env._(header)), 14)
                sheet.set_column(col, col, width, date_format if "date" in key else None)
            sheet.set_row(0, None, None, {"hidden": True})
            sheet.freeze_panes(2, 0)
        workbook.close()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "insurance_import_template.xlsx",
                "datas": base64.b64encode(output.getvalue()),
                "res_model": self._name,
                "res_id": self[:1].id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {"type": "ir.actions.act_url", "url": f"/web/content/{attachment.id}?download=true", "target": "self"}

    # -------------------------------------------------------------------------
    # Reading the file
    # -------------------------------------------------------------------------

    @api.model
    def _read_sheet_rows(self, worksheet):
        """Rows of a sheet as dicts keyed by the technical keys of row 1."""
        rows = worksheet.iter_rows(values_only=True)
        keys = [_text(key) for key in next(rows, [])]
        next(rows, None)  # headers for people
        result = []
        for index, row in enumerate(rows, start=3):
            values = {key: value for key, value in zip(keys, row) if key}
            if any(_text(value) for value in values.values()):
                values["_row"] = index
                result.append(values)
        return result

    def _read_workbook(self):
        import openpyxl  # noqa: PLC0415

        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Upload the Excel file first."))
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(base64.b64decode(self.file)), read_only=True, data_only=True)
        except Exception as error:
            raise UserError(self.env._("The file is not a valid Excel (.xlsx) file: %(error)s", error=error)) from error
        sheets = workbook.worksheets
        data = {}
        for index, (key, _title, _columns) in enumerate(SHEETS):
            data[key] = self._read_sheet_rows(sheets[index]) if index < len(sheets) else []
        workbook.close()
        return data

    @staticmethod
    def _row_key(row):
        try:
            start = _date(row.get("date_from"))
        except ValueError:
            start = _text(row.get("date_from"))
        return (_text(row.get("policy_number")), _text(row.get("insurer")).lower(), str(start or ""))

    def action_read_file(self):
        """Read the file into one line per policy. Lines already imported are
        kept; pending and failed lines are replaced by the new reading."""
        self.ensure_one()
        data = self._read_workbook()
        if not data["policies"]:
            raise UserError(self.env._("The Policies sheet has no rows (data starts on row 3)."))
        children = {"objects": {}, "installments": {}}
        for kind in children:
            for row in data[kind]:
                children[kind].setdefault(self._row_key(row), []).append(row)
        kept = {line._get_key() for line in self.line_ids.filtered(lambda l: l.state in ("done", "skipped"))}
        self.line_ids.filtered(lambda l: l.state in ("pending", "error")).unlink()
        values = []
        for row in data["policies"]:
            key = self._row_key(row)
            if key in kept:
                continue
            values.append(
                {
                    "import_id": self.id,
                    "row": row["_row"],
                    "policy_number": key[0],
                    "insurer": _text(row.get("insurer")),
                    "values_json": json.dumps(row, default=str),
                    "objects_json": json.dumps(children["objects"].get(key, []), default=str),
                    "installments_json": json.dumps(children["installments"].get(key, []), default=str),
                }
            )
        self.env["insurance.import.line"].create(values)
        return True

    # -------------------------------------------------------------------------
    # Processing
    # -------------------------------------------------------------------------

    def action_process(self):
        """Process the pending lines of this import now (one batch; the
        scheduled action processes the rest)."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.state in ("pending", "error"))
        if not lines:
            raise UserError(self.env._("There are no policies left to import."))
        self.env["insurance.import.line"]._process_batch(lines[: self._get_batch_size()])
        return True

    @api.model
    def _get_batch_size(self):
        return int(
            self.env["ir.config_parameter"].sudo().get_param("insurance_management.cron_batch_size", 200)
        ) or 200

    @api.model
    def _cron_process_imports(self):
        lines = self.env["insurance.import.line"].search([("state", "=", "pending")], order="import_id, row, id")
        batch_size = self._get_batch_size()
        remaining = len(lines)
        for start in range(0, len(lines), batch_size):
            batch = lines[start:start + batch_size]
            self.env["insurance.import.line"]._process_batch(batch)
            remaining -= len(batch)
            self.env["ir.cron"]._commit_progress(len(batch), remaining=remaining)

    def action_view_policies(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("insurance_management.insurance_policy_action")
        action["domain"] = [("id", "in", self.line_ids.policy_id.ids)]
        action["context"] = {}
        return action


class InsuranceImportLine(models.Model):
    _name = "insurance.import.line"
    _description = "Insurance import line"
    _order = "import_id, row, id"

    import_id = fields.Many2one(comodel_name="insurance.import", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="import_id.company_id", store=True)
    row = fields.Integer(string="Row")
    policy_number = fields.Char(string="Policy number")
    insurer = fields.Char(string="Insurer")
    values_json = fields.Text(string="Policy data")
    objects_json = fields.Text(string="Objects data")
    installments_json = fields.Text(string="Installments data")
    object_count = fields.Integer(string="Objects", compute="_compute_object_count")
    state = fields.Selection(
        selection=[("pending", "Pending"), ("done", "Imported"), ("skipped", "Already imported"), ("error", "Error")],
        string="Status",
        default="pending",
        required=True,
        index=True,
    )
    message = fields.Text(string="Message")
    policy_id = fields.Many2one(comodel_name="insurance.policy", string="Policy", ondelete="set null")

    def _compute_object_count(self):
        for line in self:
            line.object_count = len(json.loads(line.objects_json or "[]"))

    def _get_key(self):
        self.ensure_one()
        values = json.loads(self.values_json or "{}")
        return InsuranceImport._row_key(values)

    @api.model
    def _process_batch(self, lines):
        for line in lines:
            try:
                with self.env.cr.savepoint():
                    # Also run by the scheduled action: messages and chatter
                    # notes in the language of who created the import.
                    lang = line.import_id.create_uid.lang or self.env.lang
                    line.with_company(line.company_id).with_context(lang=lang)._process()
            except (UserError, ValueError) as error:
                line.write({"state": "error", "message": str(error.args[0] if error.args else error)})
            except Exception as error:
                _logger.exception("Insurance import failed for line %s", line.id)
                line.write({"state": "error", "message": str(error)})

    # -- lookups ---------------------------------------------------------------

    def _find_partner(self, value, flag, key):
        if not value:
            return self.env["res.partner"]
        Partner = self.env["res.partner"]
        domain = [(flag, "=", True), "|", ("company_id", "=", False), ("company_id", "=", self.company_id.id)]
        compact = value.replace("-", "").replace(".", "").replace(" ", "")
        partner = Partner.search(domain + [("vat", "in", [value, compact])], limit=2) if compact.isdigit() else Partner
        if not partner:
            partner = Partner.search(domain + [("name", "=ilike", value)], limit=2)
        if len(partner) != 1:
            raise UserError(
                self.env._("%(label)s %(value)s not found (or found twice).", label=self.env._(HEADERS[key]), value=value)
            )
        return partner

    def _find(self, model, field, value, key, extra_domain=None):
        if not value:
            return self.env[model]
        record = self.env[model].search([(field, "=ilike", value)] + (extra_domain or []), limit=2)
        if len(record) != 1:
            raise UserError(
                self.env._("%(label)s %(value)s not found (or found twice).", label=self.env._(HEADERS[key]), value=value)
            )
        return record

    # -- processing --------------------------------------------------------------

    def _process(self):
        self.ensure_one()
        env = self.env
        row = json.loads(self.values_json or "{}")
        company = self.company_id

        def date_value(key):
            label = env._(HEADERS[key])
            try:
                return _date(row.get(key))
            except ValueError as error:
                raise UserError(env._("%(label)s: invalid date %(value)s.", label=label, value=error.args[0])) from error

        def number_value(source, key):
            label = env._(HEADERS[key])
            try:
                return _number(source.get(key))
            except ValueError as error:
                raise UserError(env._("%(label)s: invalid number %(value)s.", label=label, value=source.get(key))) from error

        policy_number = _text(row.get("policy_number"))
        if not policy_number:
            raise UserError(env._("The policy number is required."))
        insurer = self._find_partner(_text(row.get("insurer")), "is_insurer", "insurer")
        if not insurer:
            raise UserError(env._("The insurer is required."))
        date_from = date_value("date_from")
        date_to = date_value("date_to")
        if not date_from or not date_to:
            raise UserError(env._("The validity dates are required."))
        existing = env["insurance.policy"].search(
            [
                ("company_id", "=", company.id),
                ("insurer_id", "=", insurer.id),
                ("policy_number", "=", policy_number),
                ("date_from", "=", date_from),
            ],
            limit=1,
        )
        if existing:
            self.write({"state": "skipped", "policy_id": existing.id, "message": env._("Already imported.")})
            return existing
        branch = self._find("insurance.branch", "name", _text(row.get("branch")), "branch")
        if not branch:
            raise UserError(env._("The branch is required."))
        producer = self._find_partner(_text(row.get("producer")), "is_insurance_producer", "producer")
        if not producer:
            raise UserError(env._("The producer is required."))
        currency = self._find("res.currency", "name", _text(row.get("currency")), "currency")
        responsible = self._find("res.users", "login", _text(row.get("responsible")), "responsible")
        payment_mode = self._find(
            "insurance.payment.mode",
            "name",
            _text(row.get("payment_mode")),
            "payment_mode",
            [("company_id", "in", (False, company.id))],
        )
        renewal_type = _text(row.get("renewal_type")) or "undefined"
        if renewal_type not in ("undefined", "renew", "no_renew"):
            raise UserError(env._("Renewal: use undefined, renew or no_renew."))
        in_progress = _text(row.get("in_progress")).lower() in YES
        continue_from = int(number_value(row, "continue_from") or 1)
        premium = number_value(row, "premium")
        premium_total = number_value(row, "premium_total") or premium
        objects = []
        for obj in json.loads(self.objects_json or "[]"):
            if not _text(obj.get("name")):
                raise UserError(env._("Objects sheet, row %(row)s: the description is required.", row=obj.get("_row")))
            objects.append(
                fields.Command.create(
                    {
                        "name": _text(obj.get("name")),
                        "license_plate": _text(obj.get("license_plate")) or False,
                        "chassis_number": _text(obj.get("chassis_number")) or False,
                        "engine_number": _text(obj.get("engine_number")) or False,
                        "sum_insured": number_value(obj, "sum_insured"),
                        "coverage": _text(obj.get("coverage")) or False,
                    }
                )
            )
        values = {
            "policy_number": policy_number,
            "insurer_id": insurer.id,
            "producer_id": producer.id,
            "branch_id": branch.id,
            "date_from": date_from,
            "date_to": date_to,
            "premium": premium,
            "premium_total": premium_total,
            "renewal_type": renewal_type,
            "company_id": company.id,
            "in_progress": in_progress,
            "continue_from_installment": continue_from if in_progress else 1,
            "unaccrued_amount": number_value(row, "unaccrued_amount"),
            "object_ids": objects,
        }
        if currency:
            values["currency_id"] = currency.id
        if responsible:
            values["user_id"] = responsible.id
        if payment_mode:
            values["payment_mode_id"] = payment_mode.id
        if _text(row.get("note")):
            values["note"] = _text(row.get("note"))
        policy = env["insurance.policy"].create(values)
        if self.import_id.confirm_policies:
            policy.action_confirm()
        count = int(number_value(row, "installment_count"))
        if count:
            first_due = date_value("first_due_date") or date_from
            installments = policy._generate_installments(
                count=count,
                first_due_date=first_due,
                total_amount=premium_total,
                payment_mode=payment_mode or None,
                continue_from=continue_from if in_progress else 1,
            )
            self._apply_installment_overrides(installments)
        if (
            in_progress
            and policy.accrual_method == "module"
            and values["unaccrued_amount"]
            and company.insurance_go_live_date
        ):
            policy.action_generate_initial_accrual()
        policy._message_log(body=env._("Imported from %(import)s, row %(row)s.", **{"import": self.import_id.name, "row": self.row}))
        self.write({"state": "done", "policy_id": policy.id, "message": False})
        return policy

    def _apply_installment_overrides(self, installments):
        """Installments sheet: amount and due date by installment number (e.g.
        an insurer billing pro rata)."""
        by_number = {installment.number: installment for installment in installments}
        for row in json.loads(self.installments_json or "[]"):
            number = int(_number(row.get("number")))
            installment = by_number.get(number)
            if not installment:
                raise UserError(
                    self.env._("Installments sheet, row %(row)s: installment %(number)s does not exist.", row=row.get("_row"), number=number)
                )
            vals = {}
            if _text(row.get("amount")):
                vals["amount"] = float_round(_number(row.get("amount")), precision_rounding=installment.currency_id.rounding)
            if _text(row.get("due_date")):
                vals["due_date"] = _date(row.get("due_date"))
            if vals:
                installment.with_context(insurance_installment_system=True).write(vals)
