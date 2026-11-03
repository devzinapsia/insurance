# Progress — insurance_management

Session-resume file. Read together with `CLAUDE.md`, `docs/ROADMAP.md` and the
requirements document
`docs/requerimiento_funcional.md` (renamed from the long original name; the
`.docx` original keeps its name and holds the two embedded diagrams).
The original prompt with the phase scopes and working rules is the source of
`docs/ROADMAP.md`; phase scope in the prompt overrides the document.

Branch: `19.0` (never touch `main` or `20.0`). Odoo source: `ODOO_19_SRC` from
`~/.claude/local-paths.env`.

## Phase status

| Phase | Status |
| --- | --- |
| Fase 1 — Control de vencimientos | Complete on branch 19.0, deployed to grupolara staging2 for testing — Hito 1 pending (the user confirms production use) |
| Fase 2 — Gestión económica y contable | Not started (needs "arrancá la Fase 2" + Hito 1) |
| Fase 3 — Siniestros, cauciones e integraciones | Not started (needs "arrancá la Fase 3" + Hito 2) |

### Fase 1 stages

| Stage | Status |
| --- | --- |
| Paso 0 — research, ambiguities, plan | Confirmed 2026-11-02 |
| (a) security, contacts, branches | Done 2026-11-02 — reviewed by the user |
| (b) policy, insured objects, lifecycle | Done 2026-11-02 — reviewed by the user |
| (c) renewal and non-renewal | Done 2026-11-02 — reviewed by the user |
| (d) settings, alerts, cron, templates + preview | Done 2026-11-02 — reviewed by the user |
| (e) documents | Done 2026-11-02 — reviewed by the user |
| (f) views, menus, filters | Done 2026-11-02 — reviewed by the user |
| (g) PDF (only if there is margin) | Done 2026-11-02 |

## Answers already given by the user (do not ask again)

- `auto_install = False` on the base module; `True` on bridge modules.
- Every new model with its own ABM gets chatter (`mail.thread` + `mail.activity.mixin`).
- Search filters / group-bys: those defined in section 10 of the document.
- New `res.partner` fields are searchable (filters "Aseguradoras", "Productores").
- Volume and chart of accounts: configurable parameters; no hardcoded account
  codes or volumes; account defaults empty with clear "missing configuration"
  messages; volume-dependent processes run in batches of configurable size.

## Decisions taken

Fase 1, Paso 0 (2026-11-02):

- **A1 Renewal**: "Renovar" creates the next draft, records the decision and the
  two-way link (`renewed_by_id` / `previous_policy_id`) without changing state.
  The final state is applied when the policy expires: Renovada if a (non-deleted)
  renewal exists, else No renovada if renewal type is "No renovar", else Vencida.
  Late renewal from Vencida → Renovada immediately. "Already renewed → no alerts"
  is keyed on `renewed_by_id`, not on state. "Renovar" is still allowed after
  "No renovar" (switches the decision, logged in chatter); both buttons hidden
  once renewed.
- **A2 Dates**: `date_to` is the last covered day (inclusive). On `date_to` the
  policy is still Por vencer ("vence hoy"); on `date_to + 1` it moves to
  Vencida / Renovada / No renovada. New setting: coverage start/end time
  (default 12:00). Details pending confirmation (see open items).
- **A3 Roles**: simplified to TWO groups, Usuario and Administrador (replaces the
  three groups of the prompt). Usuario loads/edits policies, renews, marks
  non-renewal, sees processes; cannot change settings. Administrador edits all
  settings (without needing to be Odoo system admin) and config ABMs.
- **A4 Uniqueness**: policy number unique per (insurer, company, number,
  date_from), so a renewal may reuse the number. Plus a policy flag
  "same number on renewal" (Yes/No) — exact behavior pending confirmation.
- **A5 Thresholds**: validated text "30,15,7" at company / branch / policy; empty
  inherits; most specific level with a value wins.
- **A6 Duration**: `relativedelta(date_to + 1, date_from)`; exact check
  `date_from + min <= date_to + 1 <= date_from + max`; defaults 1 / 12 months,
  default mode "block"; renewal copies the same relativedelta.
- **A7 Logo**: company logo served by Odoo (`/logo.png?company=N`) with alt text;
  layout must still work with images blocked.
- **A8–A12**: original Paso 0 proposals accepted by default (manual "request
  renewal" button only; reset to draft by Administrador from any state except
  Anulada, keeping alerts and links; state computed on confirm without emails,
  no alerts for already-passed thresholds, moving date_to resets alerts; hide
  costs is database-wide and internal alert emails carry no amounts; tags have
  no chatter, branches / insurable items / document types do).
- **A13**: `.gitignore` fixed (removed stray `cat <<EOF` line, added
  `!*/i18n/*.pot`); requirements doc renamed to `docs/requerimiento_funcional.md`.
- **Module icon**: user-provided logo (441x441 PNG, "Logo X.png") goes to
  `insurance_management/static/description/icon.png`.

- **Round 2 (2026-11-02)**:
  1. Coverage time setting: "12:00" (default) or "0:00" (never "24:00").
     Informative only (form + emails); does not change "covered today" nor
     transitions. With "0:00", wording is "until 0:00 of <date_to + 1>" since
     date_to is inclusive.
  2. On date_to the state stays Por vencer, with a "Vence hoy" ribbon/badge and
     a "Vence hoy" filter (7 states kept).
  3. date_to: expiry notice "vence hoy a las 12:00" (implicit day-0, only if not
     renewed). date_to + 1: state Vencida / Renovada / No renovada and
     "Póliza vencida" email ("venció") if not renewed, including No renovada.
  4. Two groups only: Usuario (sees and edits all policies, renews, marks
     non-renewal, sees each policy's alert history) and Administrador (same +
     configuration/settings + reset to draft). Hide costs kept as required by
     the prompt but defaults OFF; when ON, only users holding the implicit
     "Ver importes" group (assigned per user; Administrador always has it) see /
     edit amounts.
  5. Own settings form: Seguros › Configuración › Ajustes, editable by the
     insurance Administrador without Odoo system rights. Not duplicated in the
     general Odoo Settings.
  6. "Ver los procesos": user lacked context; interpreted as users seeing each
     policy's alert history and workflow (no cron/technical access).
  7. Policy flag "Keep number on renewal" (default No); Yes → renewal draft is
     born with the same number; the flag is copied to the renewal.
  8. Local test DB `insurance_p1_test` created on the ExternalSSD: tablespace
     `insurance_ssd` at `/Volumes/ExternalSSD/data/insurance_test/pgts`, Odoo
     filestore at `/Volumes/ExternalSSD/data/insurance_test/odoo-data`,
     addons path = Odoo 19 community + this repo only (no enterprise).
- **Branch names**: English source with es / es_AR translations (rule 2), data
  in `noupdate="1"`.

## Stage notes

### (a) security, contacts, branches — 2026-11-02

- Odoo 19 has no group categories for users any more: groups hang from a
  `res.groups.privilege`. Privilege "Insurance" (es: "Seguros") under the core
  category `base.module_category_services`; groups `group_insurance_user`
  (implies `base.group_user`) and `group_insurance_manager` (implies user;
  root + admin members).
- `insurance.branch`: name (translate), code (unique per company incl. shared,
  `UniqueIndex` with COALESCE), sequence, active, object_type, alert_days
  (normalized "30,15,7" via `models/insurance_tools.py`), notify_user_ids,
  company_id (empty = shared), note; chatter. ACL: user read, manager CRUD;
  multi-company rule. 10 initial branches in `data/insurance_branch_data.xml`
  (noupdate), English names + es/es_AR translations.
- `res.partner`: `is_insurer`, `is_insurance_producer` (no groups, so other apps
  never fail reading partners), shown in tab "Sales & Purchase" after group
  `misc`; filters "Insurers"/"Producers" after `type_company`. The partner
  smart button with policies is deferred to stage (b) (needs the policy model).
- Menus: root "Insurance" (user) › Configuration (manager) › Branches.
- i18n: `.pot` exported with `odoo-bin i18n export -c <conf> -d <db>
  insurance_management -l pot` (module BEFORE `-l`); es.po / es_AR.po built
  from a msgid→msgstr map, 0 empty msgstr.
- Verified: 15 tests OK; manual check that a user edit of an initial branch
  (es_AR name + alert days) survives `-u`; install → uninstall (0 leftover
  ir.model.data) → reinstall OK.
- Test DB config used: Odoo 19 community addons + this repo only, db
  `insurance_p1_test`, run with `/Users/pablocampo/devzinapsia/odoo19/venv19`.

### (b) policy, insured objects, lifecycle — 2026-11-02

Implemented as designed (see models for details):
- `insurance.policy` (`models/insurance_policy.py`): fields of 4.1 without
  accounting; 7 states with `group_expand=True`; `_get_today()` honours the
  `insurance_today` context key (cron/tests); `_get_lifecycle_state(today)`
  (base: in_force / expired from date_to + 1) and `_apply_lifecycle_state()`
  are the extension points for (c) renewed/not_renewed and (d) expiring.
  Confirm = `_check_can_confirm()` + state from dates, no emails. Internal
  state writes need context `insurance_lifecycle_write=True` (LIFECYCLE_CTX);
  direct `state` writes raise. Locked states (expired, renewed, not_renewed,
  cancelled) only accept message_/activity_ fields and
  `_get_locked_writable_fields()` (empty; (c)/(d) extend it). Reset to draft:
  insurance manager only, hook `_check_can_reset_to_draft()` for phase 2.
  Only drafts can be deleted. Reference: lazy per-company `ir.sequence`
  (`SEG/%(range_year)s/`, yearly date ranges).
- Uniqueness: `UniqueIndex (company_id, insurer_id, policy_number, date_from)
  WHERE policy_number IS NOT NULL`.
- Duration limits on `res.company` (`insurance_min_duration_months`,
  `insurance_max_duration_months`, `insurance_duration_check` warning|block,
  default 1 / 12 / block); the settings form comes in (d).
- `insurance.policy.object`: changes on non-draft policies are logged on the
  policy chatter via `mail.tracking.value` (field-level groups respected);
  removal via wizard `insurance.policy.object.exclude`; no unlink once
  confirmed. `insurance.insured.item` master (chatter); its "Seguros (n)"
  button is Phase 3 (RF-15). `insurance.policy.tag` without menu/chatter.
- res.partner smart button "Policies in force" (count of in_force/expiring
  where partner is insurer or producer; field groups = insurance user).
- Views: policy list/form/search (filters In force, Covered today, Draft, My
  policies; group by state/branch/insurer/producer), insurable items, menus
  Insurance › Policies › {Policies, Insurable items}. Kanban, calendar,
  pivot, graph and section-10 filters are stage (f).
- `uninstall_hook` (`__init__.py`): deletes policies and the on-the-fly
  sequences before Odoo removes module data (otherwise FK errors on the
  initial branches and numbering surviving a reinstall).
- Test notes: tracking values are created at pre-commit — in tests call
  `self.env.cr.flush()` between "UI transactions" and invalidate
  `message_ids`; kanban column expansion is only in
  `with_context(read_group_expand=True).web_read_group(...)`.
- Verified: 46 tests OK; install → uninstall (0 errors, 0 leftovers incl.
  sequences, with a demo policy present) → reinstall OK; form checked in the
  browser in es_AR.

### (c) renewal and non-renewal — 2026-11-02

- Policy fields: previous_policy_id / renewed_by_id (ondelete set null),
  renewal_count (history chain), keep_number_on_renewal, non_renewal_reason,
  non_renewal_date, non_renewal_sent_date, renewal_request_sent_date.
- `_get_lifecycle_state`: past date_to → renewed (renewed_by_id) /
  not_renewed (renewal_type no_renew) / expired; before date_to keeps
  in_force/expiring (stage (d) computes expiring from thresholds).
- `action_renew` (Expiring/Expired only, once): `_prepare_renewal_vals`
  copies branch, insurer, producer, responsible, company, currency,
  coverage, deductible, tags and ACTIVE objects (with insured item link);
  dates = date_to + 1 and the same relativedelta; number only if
  keep_number_on_renewal. Premiums are NOT copied (new price from insurer).
  Late renewal of Expired → Renewed at once. Deleting the renewal draft
  (`unlink`) re-applies the lifecycle of the previous policy + chatter note.
- Non-renewal: wizard `insurance.policy.non.renewal` (reason required, send
  now, cc insurer, cc responsible) → `_mark_non_renewal` +
  `_send_non_renewal_instruction` (`message_post_with_source`, comment,
  producer + copies). Request renewal opens the standard composer with the
  template. Sent dates stamped by `message_post` override using context key
  `insurance_mail_kind` (MAIL_KIND_CTX).
- Producer templates (`data/mail_template_producer_data.xml`, noupdate):
  non-renewal instruction and renewal request; lang = producer lang;
  **`use_default_to` must be False** (Odoo 19 default True ignores
  `partner_to` and looks for a partner on the record). No amounts. Helpers
  `_get_mail_objects`, `_get_mail_object_label`, `_get_mail_validity`.
- Company field `insurance_coverage_time` ("12" default / "0"), used in the
  email validity text ("hasta las 12:00 del X" / "hasta las 0:00 del X+1").
- i18n: Odoo 19 exports a template body as ONE html msgid; translated with
  ordered phrase rules (scratchpad `es_html_rules.json` + `fill_po.py`,
  which fails if any rule's English phrase remains). Previews:
  `insurance_management/preview/*.html` (rendered es_AR, not installed).
- Verified: 59 tests OK; cycle clean (0 errors, no leftover tables /
  ir.model.data / sequences / templates); previews checked in the browser.
- Pending for (d): internal alert templates (expiry notice, expired), their
  previews, automatic non-renewal sending X days before (setting + policy
  field), cron, settings form (incl. coverage time and duration limits).

### (d) settings, alerts, cron, templates — 2026-11-02

- Settings: own TransientModel `insurance.settings` (wizard/insurance_settings.py,
  menu Insurance › Configuration › Settings, insurance manager only; Odoo's
  res.config.settings needs system admin). Saves to res.company (sudo):
  insurance_alert_days (default "30"), insurance_notify_user_ids,
  min/max duration + check, coverage time, non-renewal send mode/days;
  global: hide costs (group implication) and
  `insurance_management.cron_batch_size` (default 200). Buttons: run the
  expiry process now (method_direct_trigger), branches, email templates.
- Hide costs: implicit group `group_insurance_see_amounts`; manager implies
  it in XML; user gets it ONCE via `post_init_hook` (not in XML, or every
  `-u` would undo the setting). `groups=` on policy premium, premium_total,
  sum_insured_total, deductible_amount/percent, object sum_insured, item
  reference_value. Renewal creates as sudo (after check_access) and object
  tracking reads as sudo, so users without the group can still work.
- Policy: alert_days (normalized), effective_alert_days, notify_user_ids,
  non_renewal_send_mode/days (defaults from company), alert_ids, days_left,
  expires_today (+search; ribbon "Expires today", filter). Hierarchy:
  `_get_alert_days()` policy > branch > company; `_get_notify_users()`
  union + responsible (active internal only).
- Lifecycle: before date_to → expiring when days_left <= max threshold
  (always on date_to), else in_force.
- `insurance.policy.alert` log: alert_type (expiry_notice / expired),
  threshold_days, date_to (snapshot: changing date_to restarts), sent_on,
  skipped (covered by a closer notice), recipient_ids.
- Daily process: `_cron_process_expiry` (batches + `_commit_progress`) →
  `_process_expiry_batch(policies, today)` (savepoint per policy; tests call
  this one) → `_process_expiry(today)`: state, auto non-renewal, notice
  (thresholds + implicit 0; one notice = min of pending, larger ones logged
  as skipped), "expired" notice once the day after (expired / not_renewed).
  One mail.mail per user (template lang from context
  `insurance_recipient_lang`), chatter note, one updated activity of type
  `mail_activity_type_policy_expiry` for the responsible. Cron
  `ir_cron_insurance_policy_expiry` noupdate, daily 10:00 UTC, root.
- Internal templates (`data/mail_template_alert_data.xml`): subjects via
  `_get_alert_subject()` ("vence en N días / mañana / hoy / venció"),
  "View policy" button to `/mail/view?model=insurance.policy&res_id=N`,
  what-to-do line, first 3 objects (+N), no amounts. Previews regenerated
  in `preview/` (5 files).
- Test notes: Odoo sends its own "assigned to you" notification mail to the
  responsible — filter alert mails with `is_notification = False`. The
  `sms` module (installed in the test DB) adds "SMS Delivery error" to the
  .pot.
- Verified: 86 tests OK; clean cycle (0 errors; no leftover tables, data,
  sequences, templates, crons, groups); settings form, Notifications tab and
  previews checked in the browser (es_AR).

### (e) documents — 2026-11-02

- `insurance.document.type` (chatter; name translate, sequence, active,
  description), 7 initial types (noupdate) in
  `data/insurance_document_type_data.xml`; menu Configuration › Document
  types + link in the settings form. ACL user read / manager CRUD; shared
  across companies (no company_id).
- `ir.attachment.insurance_document_type_id` (ondelete restrict).
- Policy: `attachment_ids` O2M (res_id + domain res_model), `document_count`
  (all policy attachments, chatter ones included), smart button "Documents"
  (action `insurance_policy_document_action` on ir.attachment with our list
  / search views), tab "Documents" with button "Upload document" → wizard
  `insurance.policy.document.upload` (type + file required, chatter note).
  The tab list is `create="0"`: uploads always go through the wizard, so the
  type is mandatory there; chatter files show highlighted until typed.
  `attachment_ids` is in `_get_locked_writable_fields()` (documents allowed
  on locked policies, section 5). Attachment access follows the policy
  (ACL + multi-company rule), the lock lives in policy.write only.
- uninstall_hook also unlinks attachments with res_model `insurance.%`.
- Verified: 92 tests OK; clean cycle (0 errors, no leftover attachments,
  column, data, tables); Documents tab checked in the browser (es_AR).

### (f) views, menus, filters — 2026-11-02

- Policy action: kanban (default_group_by state, all 7 columns via
  group_expand, days-left / "Expires today" badges, activities, responsible),
  list, form, calendar (date_start = date_to, color by branch), pivot (branch
  × state, premium_total), graph (bar by branch/state), activity.
- Search filters (section 10, phase 1 subset): In force, Expire in 30 days
  (`context_today() + relativedelta(days=30)`), Expired without renewal
  (state expired), Expires today, Covered today, Draft, Not to be renewed,
  My policies, End date period; group by state, branch, insurer, producer,
  responsible, end date (month). "Con cuotas impagas" is phase 2.
- Reporting menu › Upcoming expirations (`insurance_policy_expiration_action`,
  in-force domain, default filter 30 days, list sorted by date_to + calendar
  + pivot). Other section-10 reports belong to phases 2/3.
- Amount fields disappear automatically from kanban/pivot/form for users
  without `group_insurance_see_amounts` (tested).
- Reference sequence year = year of the policy start date (sequence_date =
  date_from), e.g. a policy starting in 2025 gets SEG/2025/xxxx.
- Verified: 97 tests OK; clean cycle; kanban, report (30-day filter),
  calendar checked in the browser.

### (g) PDF reports — 2026-11-02

- `report/insurance_policy_report_templates.xml`: "Policy sheet"
  (`action_report_insurance_policy`: data, amounts, insured objects active
  and removed, coverages) and "Policies in force list"
  (`action_report_insurance_policy_list`, ordered by date_to), both bound to
  the Print menu; menu Reporting › Policies in force (PDF) runs
  `action_print_policies_in_force` (server action). Report models in
  `report/insurance_policy_report.py` compute `show_amounts` server-side.
- QWeb gotcha: the example text inside a `t-field`/`t-out` element is
  rendered as the DEFAULT when the value is empty — report placeholders
  removed (a removed-on date of "01/06/2026" was showing on active
  objects). Mail templates only keep examples where the row is guarded by
  `t-if` or the value is always set.
- wkhtmltopdf is not installed on this Mac: verified with
  `_render_qweb_html` / `/report/html/...` (odoo.sh has it).

### Fase 1 closing checks — 2026-11-02

- Activity summary of the daily process written in the responsible's
  language and chatter notes in the company language (the cron runs as a
  technical user). Chatter note warns when no user to notify has an email.
- Final verification: py_compile + XML OK; uninstall (0 errors, no
  leftovers) → install with 102 tests OK (0 unexpected errors; the only
  ERROR line is the intentional isolation test) → uninstall → reinstall
  (0 warnings/errors).
- Manual test (no mail server configured, port 25 closed, nothing sent):
  branch "Flota de prueba" (30,15,7), FLT-30 (30 days) and FLT-10 (10
  days); cron run twice by hand with `method_direct_trigger` (it uses its
  own cursor: read the results from a new session). Result: 4 queued
  emails (2 users × 2 policies, es_AR subjects, company sender), FLT-10
  got one notice (15) with 30 marked covered, one activity each for the
  responsible in Spanish, second run added nothing.
- Language tests made self-sufficient: they activate es_AR and call
  `env.ref("base.module_insurance_management")._update_translations(["es_AR"])`
  (activating a language does not load module terms). Verified on a FRESH
  database without Spanish preloaded (as odoo.sh builds): 102/102 OK.
- Final four-step cycle on insurance_p1_test: install + 102 tests OK →
  verified installed (cron active, 10 branches, 7 document types, 4
  templates) → uninstall (0 errors, 0 leftovers) → reinstall (0
  warnings/errors).
- NOT verified locally: real PDF output (wkhtmltopdf missing; check headers,
  footers and page breaks on odoo.sh staging) and email rendering in dark
  mode in real clients (designed for it: explicit colors, high-contrast
  button).
- Next: Hito 1 (the user confirms production use). Fase 2 only when the user
  writes "arrancá la Fase 2".

## User guide (Knowledge)

- `docs/guia_usuario/`: end-user implementation guide in Spanish, one HTML
  file per article in `articulos/`, packed by `build_knowledge_zip.py` into
  `guia_gestion_seguros_knowledge.zip` in the format of Zinapsia's
  `knowledge_transfer` (repo devzinapsia/knowledge, format_version 1:
  manifest.json + articles/<key>/body.html). Import: Knowledge › Transfer ›
  Import. Verified on 2026-11-03: imported in a scratch Odoo 19 Enterprise DB
  (12 articles, no warnings), tables and alert boxes render natively.
- **Working rule**: update the guide with every phase and every module
  version that changes something visible to users (edit the article, add the
  entry in `articulos/11_novedades.html`, rebuild the ZIP, commit both).
- Pending: screenshots (the format supports attachments) once the UI is
  stable on staging.

## Deployments

| Date | Client repo / branch | Client commit | insurance commit | Notes |
| --- | --- | --- | --- | --- |
| 2026-11-03 | grupolara / staging2 | 0c62ef0 | 40cdbed (19.0.1.0.1: staging bugs 1-2) | Submodule update only (`git submodule update --remote --merge -- zinapsia/insurance`). |
| 2026-11-03 | grupolara / staging2 | a6bd5ef | 32b5ce7 (Fase 1) | New submodule `zinapsia/insurance` (branch 19.0, public repo, no deploy key needed). Module `insurance_management` 19.0.1.0.0 is NOT auto-installed: install "Gestión de seguros" from Apps. main and staging untouched. |

- Later commits on insurance 19.0 (e.g. 4bff8b7, CLAUDE.md lessons) do not
  change the module; grupolara keeps pointing at 32b5ce7 until the next
  `git submodule update --remote --merge -- zinapsia/insurance`.
- To check on odoo.sh staging2: real PDF output (wkhtmltopdf), emails in
  Outlook/Gmail (incl. dark mode), and that the staging database does not
  send real emails to producers before running the expiry process.
- Production (grupolara main) only after the user confirms staging2 testing
  passed (Section B branch caution).

## Staging feedback (grupolara staging2)

| # | Reported | Resolution | Version |
| --- | --- | --- | --- |
| 1 | Creating a tag from the policy shows the color as a number | Added form and list views for `insurance.policy.tag` with `widget="color_picker"` (default form showed the raw integer) | 19.0.1.0.1 |
| 2 | Producer selector empty, only "Create and edit" | By design (RF-03/RF-04): only contacts marked as producer / insurer are listed and none were marked yet on staging. Added placeholders ("Contacts marked as producer/insurer") and field help explaining where to mark them; creating from the field already marks the contact (tested) | 19.0.1.0.1 |
| 3 | Allow several responsibles | Dropped by the user: one responsible; other people go in "Users to notify" (Notifications tab), who already get every alert email | — |

## Open ambiguities (Paso 0, Fase 1)

None open for Fase 1. All Paso 0 items were resolved (see "Decisions taken").
Possible follow-ups the user may ask for: reference year from the start date
vs. creation year; default policy view kanban vs. list; copying premiums on
renewal; allowing Renew from "In force".
