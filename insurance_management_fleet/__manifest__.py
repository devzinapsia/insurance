{
    "name": "Gestión de seguros - Flota",
    "version": "19.0.1.1.0",
    "summary": "Vehículos de Flota como objetos asegurados: historial de pólizas y "
    "siniestros del vehículo y vehículos sin seguro vigente.",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Services/Insurance",
    "depends": ["insurance_management", "fleet"],
    "data": [
        "security/ir.model.access.csv",
        "views/insurance_views.xml",
        "views/fleet_vehicle_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
