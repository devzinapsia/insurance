{
    "name": "Gestión de seguros - Documentos",
    "version": "19.0.1.0.0",
    "summary": "Los documentos de las pólizas y los siniestros se centralizan en la "
    "carpeta Seguros de la app Documentos.",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Services/Insurance",
    "depends": ["insurance_management", "documents"],
    "data": [
        "data/documents_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
