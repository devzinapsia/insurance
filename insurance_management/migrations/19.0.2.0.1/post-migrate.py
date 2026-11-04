"""19.0.2.0.1.

* New "Not started" state: confirmed policies whose start date is still
  ahead move to it (until now they showed as In force or Expiring).
* Descriptions for the initial document and endorsement types.

The initial document and endorsement types are ``noupdate`` data, so an
update never writes the new descriptions: fill them here, only where the
description is still empty (a description written by the users is never
replaced), in English and in the active Spanish languages.
"""

from odoo import SUPERUSER_ID, api

DESCRIPTIONS = {
    "insurance_document_type_policy": (
        "Policy issued by the insurer, with its conditions and annexes.",
        "Póliza emitida por la aseguradora, con sus condiciones y anexos.",
    ),
    "insurance_document_type_endorsement": (
        "Endorsement issued by the insurer that modifies the policy (objects, sums insured, coverages, validity).",
        "Endoso emitido por la aseguradora que modifica la póliza (objetos, sumas aseguradas, coberturas, vigencia).",
    ),
    "insurance_document_type_certificate": (
        "Certificate proving the coverage to third parties (e.g. a client, a lessor or a vehicle check).",
        "Certificado que acredita la cobertura ante terceros (por ejemplo, un cliente, un locador o un control vehicular).",
    ),
    "insurance_document_type_payment_receipt": (
        "Proof of payment of a premium installment.",
        "Comprobante de pago de una cuota del premio.",
    ),
    "insurance_document_type_invoice": (
        "Invoice from the insurer for the premium or an endorsement.",
        "Factura de la aseguradora por el premio o por un endoso.",
    ),
    "insurance_document_type_claim_report": (
        "Claim report filed with the insurer and its supporting documents.",
        "Denuncia de siniestro presentada ante la aseguradora y su documentación respaldatoria.",
    ),
    "insurance_document_type_other": (
        "Any other document related to the policy.",
        "Cualquier otro documento relacionado con la póliza.",
    ),
    "insurance_endorsement_type_add_object": (
        "Adds insured objects to the policy from the endorsement date, usually with an additional premium. E.g. a new pickup truck joins the fleet policy.",
        "Agrega objetos asegurados a la póliza desde la fecha del endoso, normalmente con premio adicional. Ej.: se incorpora una camioneta nueva a la póliza de flota.",
    ),
    "insurance_endorsement_type_remove_object": (
        "Removes insured objects from the endorsement date; they stay as history with the reason, usually with a premium refund. E.g. a fleet vehicle is sold.",
        "Da de baja objetos asegurados desde la fecha del endoso; quedan como historial con el motivo, normalmente con devolución de premio. Ej.: se vende un vehículo de la flota.",
    ),
    "insurance_endorsement_type_increase_sum": (
        "Raises the sum insured of some objects, with an additional premium. E.g. the stock of a warehouse grows before the high season.",
        "Aumenta la suma asegurada de algunos objetos, con premio adicional. Ej.: crece la mercadería de un depósito antes de la temporada alta.",
    ),
    "insurance_endorsement_type_decrease_sum": (
        "Lowers the sum insured of some objects, usually with a premium refund. E.g. a vehicle is revalued at its current market price.",
        "Reduce la suma asegurada de algunos objetos, normalmente con devolución de premio. Ej.: se actualiza el valor de un vehículo a su precio de mercado.",
    ),
    "insurance_endorsement_type_coverage_change": (
        "Changes the coverages or clauses of the policy or of some objects. E.g. a vehicle goes from third party cover to all risks.",
        "Cambia las coberturas o cláusulas de la póliza o de algunos objetos. Ej.: un vehículo pasa de terceros completo a todo riesgo.",
    ),
    "insurance_endorsement_type_data_change": (
        "Changes administrative data without changing the risk, such as the producer. E.g. the company changes its insurance producer.",
        "Cambia datos administrativos sin modificar el riesgo, como el productor. Ej.: la empresa cambia de productor de seguros.",
    ),
    "insurance_endorsement_type_extension": (
        "Extends the validity to a new end date, usually with an additional premium. E.g. the policy is extended one month while the renewal is negotiated.",
        "Extiende la vigencia hasta una nueva fecha, normalmente con premio adicional. Ej.: se prorroga la póliza un mes mientras se negocia la renovación.",
    ),
    "insurance_endorsement_type_cancellation": (
        "Ends the policy before its end date: installments not billed are cancelled and the insurer may refund premium. E.g. the insured asset is sold or the contract a surety bond guaranteed ends.",
        "Termina la póliza antes de su vencimiento: se anulan las cuotas no facturadas y la aseguradora puede devolver premio. Ej.: se vende el bien asegurado o termina el contrato que garantizaba una caución.",
    ),
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Policy = env["insurance.policy"]
    not_started = Policy.search([("state", "in", ("in_force", "expiring")), ("date_from", ">", Policy._get_today())])
    not_started._apply_lifecycle_state()
    spanish = [code for code, _name in env["res.lang"].get_installed() if code.startswith("es")]
    for xmlid, (english, translation) in DESCRIPTIONS.items():
        record = env.ref(f"insurance_management.{xmlid}", raise_if_not_found=False)
        if not record or record.with_context(lang="en_US").description:
            continue
        record.with_context(lang="en_US").description = english
        # Not a plain write per language: when en_US is not an active
        # language, writing in Spanish also replaces the English source.
        if spanish:
            record.update_field_translations("description", dict.fromkeys(spanish, translation))
