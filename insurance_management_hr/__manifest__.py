{
    "name": "Gestión de seguros - Empleados",
    "version": "19.0.1.0.0",
    "summary": "Empleados como objetos asegurados (accidentes personales, vida): "
    "historial de pólizas y siniestros del empleado.",
    "author": "Zinapsia",
    "website": "https://www.zinapsia.com",
    "license": "AGPL-3",
    "category": "Services/Insurance",
    "depends": ["insurance_management", "hr"],
    "data": [
        "views/insurance_views.xml",
        "views/hr_employee_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
