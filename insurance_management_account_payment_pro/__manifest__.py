{
    "name": "Gestión de seguros - Pagos de adhoc",
    "version": "19.0.1.0.0",
    "summary": "Las órdenes de pago de las cuotas de seguros pagan solo la "
    "cuota de la factura (account_payment_pro).",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Services/Insurance",
    "depends": ["insurance_management", "account_payment_pro"],
    "data": [],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
