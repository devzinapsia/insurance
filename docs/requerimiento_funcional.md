# Requerimiento Funcional – Módulo de Gestión de Seguros (Odoo 19)

Nov 2, 2026 · @Pablo

## 1. Objetivo y alcance

El módulo **Gestión de Seguros** (`insurance_management`) centraliza en Odoo 19 todas las pólizas que contrata la empresa: vigencia, costo, cuotas, endosos, documentación y vencimientos, integrado con Contabilidad y con alertas automáticas por correo.

El objetivo de negocio tiene tres partes: que ninguna póliza venza sin que alguien lo sepa, que el costo del seguro se impute en el período que corresponde, y que póliza, endosos, facturas y comprobantes estén en un solo lugar.

**Incluido en el alcance**

- Alta, modificación y baja de pólizas por ramo (automotor, caución, accidentes personales, incendio, integral de comercio, responsabilidad civil, vida, transporte, etc.), con ramos como ABM y valores por defecto.
- Control de vigencia (desde / hasta), renovación y no renovación.
- Productor y Compañía aseguradora como contactos del sistema.
- Vinculación de facturas de proveedor con la póliza, sus endosos y sus cuotas.
- Endosos que amplían o reducen el objeto asegurado, la suma asegurada o la prima.
- Plan de cuotas con débito automático (banco o tarjeta) o pagos diferidos, en pesos o dólares.
- Alertas internas y correo al productor con plantillas propias.
- Documentación adjunta (póliza, certificados, comprobantes).
- Siniestros con gestión contable del recupero, y cauciones hasta su liberación.
- Carga inicial de pólizas en curso para el go live.
- Parámetros generales en Ajustes, reemplazables por ramo y por póliza.

**Fuera del alcance de la fase 1**: cotización en línea vía API con aseguradoras, gestión desde el punto de vista de un productor o broker (el módulo es para la empresa asegurada) y cálculos actuariales.

**Dependencias de Odoo 19**: `base`, `mail`, `contacts`, `account`, `product`, `fleet` y `hr` (estos dos, confirmados en el cliente). Opcionales: `analytic`, `documents` (Enterprise), `account_accountant` (Enterprise, gastos diferidos), `l10n_latam_check` (cheques propios diferidos), `sale` y `project` (vincular cauciones).

## 2. Glosario

| Término | Definición en el módulo |
| --- | --- |
| Póliza | Contrato de seguro entre la empresa (asegurado) y la compañía aseguradora. Tiene número, vigencia, ramo, coberturas y costo. |
| Ramo | Rubro del seguro: automotor, caución, accidentes personales, incendio, RC, vida, etc. Define qué tipo de objeto se asegura y valores por defecto. |
| Vigencia | Período de cobertura, siempre con fecha desde y hasta. Entre 1 y 12 meses. |
| Compañía aseguradora | Proveedor que emite la póliza y la factura. Es un contacto (`res.partner`). |
| Productor | Productor asesor de seguros que intermedia la póliza. Es un contacto (`res.partner`). |
| Objeto asegurado | Lo que se cubre: un vehículo, un bien, una persona, un contrato (en caución). |
| Suma asegurada | Monto máximo que paga la aseguradora ante un siniestro, por objeto y total. |
| Prima | Costo técnico del seguro, sin impuestos ni recargos. |
| Premio | Lo que efectivamente paga la empresa: prima + impuestos + recargos. Es el importe a facturar y cuotificar. |
| Endoso | Modificación de una póliza vigente: alta o baja de objetos, cambio de suma, de cobertura o de datos. Puede generar cobro o devolución. |
| Cuota | Fracción del premio con su fecha de vencimiento y forma de pago. |
| Franquicia | Parte del daño que queda a cargo del asegurado. |
| Caución | Seguro que garantiza el cumplimiento de una obligación ante un tercero (licitación, contrato, alquiler, aduana). |
| Siniestro | Hecho cubierto que da lugar a un reclamo a la aseguradora. |
| Renovación | Nueva póliza para el período siguiente, vinculada a la anterior. |

## 3. Actores, roles y permisos

Se proponen tres grupos de seguridad propios, en una categoría "Seguros", más el uso de los grupos estándar de Contabilidad para todo lo que genera asientos.

| Grupo | Quién | Puede |
| --- | --- | --- |
| Seguros / Usuario | Personal que consulta coberturas (flota, RRHH, comercial) | Ver pólizas, objetos asegurados, endosos y documentos. Descargar certificados. No ve importes si se activa la opción de ocultar costos. |
| Seguros / Gestor | Responsable administrativo de seguros | Crear y editar pólizas, endosos, cuotas y siniestros. Renovar, marcar no renovar, enviar correos al productor. |
| Seguros / Administrador | Jefe de Administración | Todo lo anterior + configuración (ramos, tipos de endoso, días de alerta, usuarios notificados, plantillas). Anular pólizas. |
| Contabilidad (estándar) | Equipo contable | Vincular y validar facturas, confirmar pagos y débitos, generar devengamientos. |

**Actores externos** (no son usuarios, son contactos): Compañía aseguradora y Productor. Reciben correos pero no acceden al sistema en la fase 1.

**Reglas de registro**: multiempresa por `company_id`; el grupo Usuario solo ve pólizas de sus empresas permitidas. Opcionalmente, restringir por responsable o por ramo.

## 4. Modelo de datos

La póliza es el registro central; de ella cuelgan objetos asegurados, endosos, cuotas, facturas, siniestros y adjuntos. Todos los modelos heredan `mail.thread` y `mail.activity.mixin` para tener chatter, seguimiento de cambios y adjuntos.

### 4.1 Póliza (`insurance.policy`)

| Campo | Tipo | Obligatorio | Descripción / regla |
| --- | --- | --- | --- |
| Referencia interna | Char (secuencia) | Sí | Automática, ej. SEG/2026/0001. |
| Número de póliza | Char | Sí | El que asigna la aseguradora. Único por aseguradora y empresa. |
| Ramo | Many2one `insurance.branch` | Sí | Define tipo de objeto y valores por defecto. |
| Compañía aseguradora | Many2one `res.partner` | Sí | Filtrado a contactos marcados como aseguradora. |
| Productor | Many2one `res.partner` | Sí | Filtrado a contactos marcados como productor. |
| Vigencia desde / hasta | Date | Sí | Hasta > desde. Duración entre 1 y 12 meses. |
| Duración (meses) | Integer, calculado | — | Para reportes y validación. |
| Estado | Selection | Sí | Ver sección 5. |
| Tipo de renovación | Selection | Sí | Renovar / No renovar / A definir. |
| Póliza anterior / Renovada por | Many2one `insurance.policy` | No | Encadena el historial de renovaciones. |
| Responsable | Many2one `res.users` | Sí | Recibe alertas y actividades. |
| Usuarios a notificar | Many2many `res.users` | No | Se suman a los definidos en configuración. |
| Días de aviso | Integer | No | Por defecto, el del ramo o la configuración. |
| Moneda | Many2one `res.currency` | Sí | Permite pólizas en USD. |
| Suma asegurada total | Monetary, calculado | — | Suma de objetos activos. |
| Prima / Premio | Monetary | Sí | Premio = lo que se paga; base de las cuotas. |
| Franquicia | Monetary / Char | No | Puede ser monto o porcentaje. |
| Coberturas | Html o líneas | No | Descripción de coberturas y cláusulas. |
| Forma de pago | Selection | Sí | Débito automático / Pagos diferidos / Contado. |
| Diario de pago | Many2one `account.journal` | Si es débito | Uno de los diarios habilitados en Ajustes: banco, tarjeta de crédito o cheques. |
| Cuenta de gasto | Many2one `account.account` | No | Por defecto, la del ramo. |
| Distribución analítica | Json analítico | No | Centro de costo, vehículo, proyecto. |
| Empresa | Many2one `res.company` | Sí | Multiempresa. |
| Etiquetas | Many2many | No | Clasificación libre. |

**Parámetros propios de cada póliza.** Toman el valor de Ajustes (o del ramo) al crear la póliza y se pueden cambiar en cada una (ver 4.9).

| Parámetro | Opciones |
| --- | --- |
| Modo de facturación | Una factura por póliza / Una factura por cuota. |
| Método de devengamiento | Gastos diferidos estándar (solo Enterprise) / Devengamiento del módulo / Sin devengamiento (gasto directo). |
| Estado del pago generado | Borrador (para revisar) / Validado. |
| Envío del correo de no renovación | Manual / Automático X días antes del vencimiento. |
| Moneda de pago | Moneda de la póliza / Pesos al tipo de cambio del día de pago. |
| Cuenta de gasto, cuenta a devengar y analítica | Propuestas desde el ramo y Ajustes, editables. |
| Carga inicial | Marca de póliza en curso + cuota desde la que continúa (ej. 4/12). Ver RF-11. |

### 4.2 Ramo (`insurance.branch`)

| Campo | Descripción |
| --- | --- |
| Nombre y código | Automotor, Caución, Accidentes personales, etc. |
| Tipo de objeto | Vehículo / Persona / Bien / Contrato / Genérico. Define qué campos se muestran en los objetos. |
| Cuenta de gasto y producto | Valores por defecto para facturas y devengamiento. |
| Días de aviso por defecto | Ej. 30 para automotor, 60 para caución. |
| Requiere vehículo de flota | Si se marca, el objeto debe vincularse a `fleet.vehicle`. |

El ramo es un ABM propio, accesible desde Seguros › Configuración › Ramos y desde un enlace en Ajustes › Seguros. Cada ramo define además usuarios adicionales a notificar y las cuentas de siniestros.

El módulo instala estos ramos como datos iniciales editables (no se pisan al actualizar el módulo); los días de aviso son una propuesta.

| Ramo | Tipo de objeto | Días de aviso |
| --- | --- | --- |
| Automotor | Vehículo | 30 |
| Caución | Contrato | 60 |
| Accidentes personales | Persona | 30 |
| Vida colectivo | Persona | 30 |
| Incendio | Bien | 30 |
| Integral de comercio | Bien | 30 |
| Robo | Bien | 30 |
| Equipos electrónicos | Bien | 30 |
| Transporte de mercaderías | Bien | 30 |
| Responsabilidad civil | Genérico | 30 |

### 4.3 Objeto asegurado (`insurance.policy.object`)

**Póliza y objeto asegurado no son lo mismo.** La póliza es el contrato (número, vigencia, aseguradora, productor, premio); el objeto asegurado es cada cosa o persona que ese contrato cubre. Ejemplo: una póliza de flota con 15 camionetas es 1 póliza y 15 objetos, cada uno con su patente, suma asegurada y cobertura.

Separarlos permite que un endoso agregue o quite una camioneta sin crear otra póliza, que el vehículo de Flota muestre en qué póliza está, y que un siniestro se registre sobre el objeto afectado. En pólizas de un solo bien (incendio del depósito) habrá un único objeto.

**Historial de seguros del objeto.** Cada renovación crea líneas de objeto nuevas, por eso el historial se apoya en un registro maestro que no cambia entre pólizas: el vehículo de Flota, el empleado o un **Bien asegurable** (`insurance.insured.item`) para lo que no existe en Odoo, como un depósito, un local o un equipo. La línea de objeto apunta a ese maestro y la renovación copia el vínculo.

En el maestro, el botón inteligente **Seguros (n)** abre el historial completo, de la póliza más reciente a la más antigua:

| Columna | De dónde sale |
| --- | --- |
| Póliza y número | Póliza |
| Ramo y aseguradora | Póliza |
| Período cubierto | Vigencia de la póliza, o fechas de alta y baja del objeto si entró o salió por endoso |
| Suma asegurada y cobertura | Línea de objeto |
| Endosos que lo afectaron | Endosos |
| Estado de la póliza | Póliza |

Junto a él, el botón **Siniestros (n)** muestra los siniestros del objeto en todas sus pólizas, y el indicador **Asegurado hoy** (sí / no) alimenta la alerta de vehículos sin póliza vigente.

**Bien asegurable (`insurance.insured.item`)**: nombre, tipo (inmueble, mercadería, equipo, otro), ubicación, identificación (número de serie, partida), valor de referencia, vínculo opcional al activo fijo y empresa. Se crea desde la línea de objeto o desde su propio menú.

| Campo | Descripción |
| --- | --- |
| Póliza | Many2one, obligatorio. |
| Descripción | Texto libre del bien. |
| Vehículo / Empleado / Bien | Vínculos opcionales a `fleet.vehicle`, `hr.employee` o un activo, según el tipo del ramo. |
| Datos específicos | Patente, chasis, motor (automotor); beneficiario, expediente, contrato (caución). |
| Suma asegurada | Monetary. |
| Cobertura | Ej. Terceros completo, Todo riesgo con franquicia. |
| Alta / baja | Fechas y endoso que lo incorporó y lo excluyó. Se conserva el historial: nunca se borra. |

### 4.4 Endoso (`insurance.endorsement`)

| Campo | Descripción |
| --- | --- |
| Póliza y número de endoso | El número lo asigna la aseguradora. |
| Fecha de emisión y de vigencia | La vigencia debe estar dentro de la de la póliza (salvo prórroga). |
| Tipo | Alta de objeto, Baja de objeto, Aumento de suma, Reducción de suma, Cambio de cobertura, Cambio de datos, Prórroga de vigencia, Anulación. |
| Líneas | Objetos que entran, salen o cambian, con suma anterior y nueva. |
| Diferencia de premio | Monetary con signo: positivo = cobro adicional, negativo = devolución. |
| Factura / Nota de crédito | Vínculo a `account.move`. |
| Estado | Borrador / Confirmado / Cancelado. |

### 4.5 Cuota (`insurance.installment`)

| Campo | Descripción |
| --- | --- |
| Póliza y endoso de origen | El endoso es opcional (cuotas adicionales por un endoso). |
| Número y vencimiento | 1/12, 2/12… con fecha de vencimiento. |
| Importe y moneda | Monetary. |
| Modo de pago | Débito automático / Cheque diferido / Transferencia programada. |
| Diario | Banco o tarjeta. |
| Pago | Many2one `account.payment` generado. |
| Factura | La factura que cancela la cuota. |
| Estado | Pendiente / Programada / Pagada / Vencida impaga / Cancelada. |

### 4.6 Siniestro (`insurance.claim`)

| Campo | Descripción |
| --- | --- |
| Número interno y número de la aseguradora | Secuencia propia + el número de siniestro que asigna la compañía. |
| Póliza y objeto afectado | El objeto puede ser un vehículo, un empleado o un bien. |
| Fechas | Ocurrencia, denuncia, aprobación, cobro estimado (según la liquidación de la aseguradora) y cobro real. |
| Tipo | Daño propio, Robo, Responsabilidad civil (reclamo de un tercero), Accidente de persona, Ejecución de caución. |
| Descripción y terceros | Lugar, relato, terceros involucrados, liquidador, taller o proveedor. |
| Importes | Daño estimado, franquicia, reclamado, aprobado y cobrado. Diferencia calculada entre reclamado y cobrado. |
| Destino del recupero | Cobro a la empresa / Pago directo al taller o proveedor / Reposición del bien. |
| Estado | Borrador, Denunciado, En análisis, Aprobado, Rechazado, Cobrado, Cerrado. |
| Asientos | Crédito a cobrar a la aseguradora, cobro y franquicia (sección 8.6). |

**Efecto del siniestro sobre la póliza.** La póliza no siempre se consume: depende de si el objeto se pierde y del ramo. El siniestro tiene el campo Efecto sobre la póliza y, al aprobarlo, el módulo propone la acción correspondiente.

| Efecto | Caso típico | Qué hace el módulo |
| --- | --- | --- |
| Sin efecto | Daño parcial en automotor, responsabilidad civil | La póliza y el objeto siguen igual. |
| Reduce la suma asegurada | Incendio, robo o equipos con daño parcial, según condiciones de la póliza | Descuenta lo indemnizado de la suma disponible del objeto y ofrece un endoso de rehabilitación de suma, con premio adicional. |
| Pérdida total del objeto | Destrucción total o robo del vehículo; muerte o incapacidad total en accidentes personales | Genera un endoso de baja del objeto con motivo siniestro. Si no quedan objetos, la póliza pasa a Anulada con motivo Pérdida total por siniestro. Ofrece **Asegurar reemplazo**: alta en la misma póliza o póliza nueva copiada. |
| Ejecución de caución | El beneficiario ejecuta la garantía | La garantía pasa a Ejecutada y la póliza termina. Ver la nota de caución. |

Si la póliza termina antes de tiempo, el devengamiento se detiene. El saldo a devengar se imputa a gasto o se cancela con la nota de crédito si la aseguradora devuelve premio. Las cuotas pendientes se cancelan o se compensan con la indemnización, según la liquidación de la aseguradora.

**En caución, el sentido contable se invierte.** La empresa es el tomador: si el beneficiario ejecuta la garantía, la aseguradora le paga y luego repite contra la empresa. No hay recupero sino una deuda con la aseguradora, que el módulo registra como pasivo y no como crédito a cobrar.

### 4.7 Datos de caución

Se muestran en la póliza cuando el ramo es de tipo Contrato.

| Campo | Descripción |
| --- | --- |
| Beneficiario | Tercero ante quien se garantiza: organismo, cliente, locador, aduana. Contacto del sistema. |
| Tipo de caución | Mantenimiento de oferta, Cumplimiento de contrato, Anticipo financiero, Fondo de reparo, Alquiler, Aduanera, Judicial. |
| Obligación garantizada | Licitación, contrato, orden de venta o proyecto (vínculos opcionales). |
| Monto garantizado | Monetary. |
| Fin de la obligación | Puede ser posterior a la vigencia: la aseguradora sigue refacturando hasta que se acredita la liberación. |
| Estado de la garantía | Emitida, Entregada al beneficiario, Liberada, Devuelta a la aseguradora, Ejecutada. |
| Constancia de liberación | Documento adjunto obligatorio para pasar a Liberada. |

### 4.8 Herencias sobre modelos estándar

| Modelo | Agregado |
| --- | --- |
| `res.partner` | Marcas "Es aseguradora" y "Es productor"; botón inteligente de pólizas. |
| `account.move` | Campos Póliza y Endoso; botón para ir a la póliza. |
| `account.payment` | Campo Cuota de seguro, para trazabilidad. |
| `fleet.vehicle` | Pólizas del vehículo y alerta "sin seguro vigente" (si se instala `fleet`). |
| `res.config.settings` | Parámetros generales del módulo (ver 4.9). |

`hr.employee` también se hereda: pólizas donde el empleado figura como asegurado (accidentes personales, vida) y siniestros asociados. Flota y Empleados están confirmados en el cliente, por lo que ambas integraciones entran en la fase 1.

### 4.9 Parámetros en Ajustes y jerarquía de valores

Ajustes › Seguros define los valores generales; el ramo y la póliza pueden reemplazarlos, y siempre gana el más específico: Póliza > Ramo > Ajustes.

| Parámetro | Ajustes | Ramo | Póliza |
| --- | --- | --- | --- |
| Usuarios a notificar | Sí | Adicionales | Adicionales |
| Días de aviso (uno o varios umbrales) | Sí | Sí | Sí |
| Diarios habilitados para pagar pólizas (banco, tarjeta, cheques) | Sí | — | Elige uno |
| Estado del pago generado (borrador / validado) | Sí | — | Sí |
| Método de devengamiento | Sí | — | Sí |
| Modo de facturación (por póliza / por cuota) | Sí | Sí | Sí |
| Envío del correo de no renovación (manual / automático) | Sí | — | Sí |
| Cuenta de gasto | Sí | Sí | Sí |
| Cuenta de seguros a devengar (activo) | Sí | — | Sí |
| Diario de devengamiento | Sí | — | — |
| Distribución analítica | — | Sí | Sí |
| Cuentas de siniestros (crédito a cobrar, recupero, franquicia) | Sí | Sí | — |
| Plantillas de correo | Sí | — | — |

Desde Ajustes › Seguros también se accede a los ABM de Ramos, Tipos de endoso y Tipos de documento.

## 5. Ciclo de vida de la póliza

&#91;embedded content: ciclo de vida de la póliza · 7 estados\]

La póliza nace en Borrador y se confirma con número y vigencia; el proceso diario la pasa a Por vencer al llegar al primer aviso, y al vencer termina en uno de tres estados según la decisión tomada.

**Reglas de transición**

- Solo las pólizas Vigentes o Por vencer admiten endosos.
- Renovar está disponible en Por vencer y en Vencida (renovación tardía); crea la póliza siguiente en Borrador, vinculada a la anterior.
- No renovar puede marcarse en cualquier momento antes del vencimiento; el estado No renovada se aplica al llegar la fecha hasta.
- Anular requiere un endoso de anulación o un siniestro de pérdida total, es posible desde Vigente o Por vencer y puede generar nota de crédito.
- Vencida, Renovada, No renovada y Anulada quedan en solo lectura, salvo adjuntos y facturas.
- Volver a Borrador solo lo puede hacer un Administrador y solo si no hay facturas ni pagos vinculados.

## 6. Requerimientos funcionales

Cada requerimiento indica la regla de negocio y el criterio de aceptación con el que se valida en las pruebas.

### RF-01 Vigencia y número de póliza

- Toda póliza tiene número (de la aseguradora), fecha desde y fecha hasta; los tres son obligatorios para confirmarla.
- La fecha hasta debe ser mayor a la fecha desde; la duración debe estar entre 1 y 12 meses (configurable: advertencia o bloqueo).
- El número de póliza es único por aseguradora y empresa.
- Criterio: no se puede confirmar una póliza sin número o con vigencia fuera de rango; el sistema muestra el mensaje de error correspondiente.

### RF-02 Renovación al finalizar la vigencia

- La póliza tiene un campo Tipo de renovación: Renovar / No renovar / A definir.
- Botón **Renovar**: crea una nueva póliza en borrador que copia ramo, aseguradora, productor, objetos activos y coberturas; la vigencia nueva arranca el día siguiente al vencimiento con la misma duración. La póliza original pasa a Renovada y quedan vinculadas.
- El número de la nueva póliza puede quedar vacío hasta que la aseguradora lo emita (la póliza no se confirma sin él).
- Botón **No renovar**: pasa la póliza a No renovada al vencer, registra el motivo y ofrece enviar el correo al productor (RF-09).
- Criterio: desde una póliza renovada se navega a la anterior y a la siguiente; el historial completo se ve en un botón inteligente.

### RF-03 Productor de la póliza

- Campo Productor obligatorio, ligado a `res.partner` con la marca Es productor.
- En la ficha del contacto, botón inteligente con sus pólizas vigentes.
- Criterio: el selector de productor solo muestra contactos marcados como productor.

### RF-04 Compañía aseguradora (proveedor)

- Campo Compañía aseguradora obligatorio, ligado a `res.partner` con la marca Es aseguradora.
- Es el proveedor por defecto de las facturas y pagos de la póliza.
- Criterio: al crear la factura desde la póliza, el proveedor es la aseguradora.

### RF-05 Asociación de la factura con el seguro

- Se agregan los campos Póliza, Endoso y Cuota en la factura de proveedor (`account.move`).
- El **modo de facturación** es una propiedad de la póliza: una factura por póliza (premio total o por endoso) o una factura por cuota, vinculada a esa cuota.
- Dos caminos: crear la factura desde la póliza, el endoso o la cuota (botón **Crear factura**, en borrador), o cargarla en Contabilidad y elegir la póliza.
- Al elegir la póliza, se proponen cuenta, distribución analítica y fechas de devengamiento según el método de la póliza (sección 8).
- En facturación por póliza, la factura toma vencimientos múltiples iguales a las cuotas, así la deuda por vencimiento y el flujo de fondos muestran cada cuota.
- La póliza muestra un botón inteligente Facturas con total facturado, pagado y saldo.
- Criterio: una factura vinculada se ve desde la póliza y la póliza desde la factura.

### RF-06 Endosos

- Solo se cargan endosos sobre pólizas Vigentes o Por vencer.
- Tipos: alta de objeto, baja de objeto, aumento o reducción de suma, cambio de cobertura, cambio de datos, prórroga y anulación.
- Al confirmar el endoso se actualizan los objetos asegurados (entran, salen o cambian su suma) sin borrar el historial.
- Si hay diferencia de premio: positiva genera factura y cuotas adicionales; negativa genera nota de crédito y ajusta cuotas pendientes.
- Criterio: después de un endoso de baja, el objeto figura como excluido con fecha y número de endoso, y la suma asegurada total se recalcula.

### RF-07 Cuotas y forma de pago

- Botón **Generar cuotas**: crea de una vez todas las cuotas de la vigencia (ej. 12), con vencimiento mensual o fechas manuales, editables antes de confirmar.
- **El cierre de ejercicio no cambia las cuotas.** Se generan todas aunque la vigencia cruce el cierre, para que el flujo de fondos muestre todos los pagos comprometidos. La separación entre ejercicios la hace el devengamiento: al cierre, lo no devengado queda en el activo y se imputa al ejercicio siguiente. Generarlas mes a mes con un proceso se descarta porque ocultaría pagos futuros.
- La suma de las cuotas debe igualar el premio más los endosos; si no, se muestra la diferencia.
- Cada cuota tiene modo de pago (débito automático, cheque o echeq diferido, transferencia programada) y un diario elegido entre los habilitados en Ajustes (bancos, tarjetas de crédito, cheques).
- Todos los modos se comportan igual: el pago se genera con su fecha y en el estado definido para la póliza (borrador o validado; el valor por defecto viene de Ajustes).
- **Débito automático**: un proceso diario genera el pago en la fecha de vencimiento y lo concilia con la factura.
- **Pagos diferidos**: al confirmar el plan se generan los pagos con fecha futura o los cheques diferidos con su fecha de pago, visibles en la contabilidad y en el flujo de fondos futuro.
- Criterio: el reporte de cuotas muestra, por mes, lo pendiente, lo programado y lo pagado de todas las pólizas, incluidas las cuotas posteriores al cierre.

### RF-08 Alertas internas de vencimiento

- Un proceso diario detecta pólizas cuya fecha hasta está a X días (configurable por póliza, ramo o general; se admiten varios avisos, ej. 30, 15 y 7).
- Envía la plantilla **Aviso de vencimiento** a los usuarios a notificar y al responsable, y crea una actividad al responsable.
- El día del vencimiento envía la plantilla **Póliza vencida** si no fue renovada.
- Cada aviso se envía una sola vez por póliza y umbral (se registra en el chatter).
- Criterio: una póliza que vence en 30 días genera exactamente un correo y una actividad en esa fecha.

### RF-09 Correo al productor para no renovar

- Plantilla específica **Instrucción de no renovación**, dirigida al productor, con copia opcional a la aseguradora y al responsable.
- El envío es un parámetro de la póliza (valor por defecto en Ajustes): **Manual**, con el botón No renovar, o **Automático**, X días antes del vencimiento cuando el tipo de renovación es No renovar.
- El correo queda en el chatter como constancia y la póliza registra la fecha de envío.
- Criterio: el productor recibe el correo con número de póliza, ramo, vigencia y objetos asegurados; queda trazado en la póliza.

### RF-10 Documentos adjuntos

- Adjuntos desde el chatter y una pestaña Documentos con tipo de documento: Póliza, Endoso, Certificado de cobertura, Comprobante de pago, Factura, Denuncia de siniestro, Otro.
- Botón inteligente con el conteo de documentos; los adjuntos de endosos y facturas vinculadas se ven también desde la póliza.
- Si está instalado `documents` (Enterprise), se envían a una carpeta Seguros.
- Criterio: desde la póliza se accede a todos los documentos propios y de sus endosos sin cambiar de pantalla.

### RF-11 Carga inicial de pólizas en curso (go live)

- La póliza tiene la marca **Póliza en curso** para cargar seguros ya vigentes con todos sus datos: objetos, coberturas, endosos previos (como históricos) y documentos.
- Se indica la cuota desde la que continúa, ej. 4 de 12: las cuotas 1 a 3 se crean en estado Pagada (histórica), sin pagos ni asientos; de la 4 a la 12 se generan normalmente.
- Se informa el importe aún no devengado a la fecha de go live, que debe coincidir con el saldo de apertura de la cuenta de seguros a devengar; el devengamiento arranca en el mes del go live.
- Si queda deuda con la aseguradora, se vincula la factura de apertura (o el saldo inicial del proveedor) a la póliza.
- Importación masiva desde Excel de pólizas, objetos y cuotas con la misma lógica.
- Criterio: una póliza cargada en 4/12 muestra 3 cuotas históricas y 9 pendientes, y el devengamiento genera solo los meses restantes sin duplicar el gasto ya registrado.

### RF-12 Siniestros y recupero

- Alta desde la póliza, el objeto, el vehículo o el empleado; aviso si la póliza no estaba vigente a la fecha de ocurrencia.
- Estados y documentos propios (denuncia, fotos, presupuestos, informe del liquidador).
- Gestión contable del recupero, con cuentas configurables: al aprobar, crédito a cobrar a la aseguradora contra la cuenta de recupero; la franquicia queda como gasto; el cobro cancela el crédito.
- Si la aseguradora paga directamente al taller o proveedor, se compensa el crédito contra la factura del proveedor, sin movimiento de fondos.
- Alerta por siniestros sin movimiento en X días (parámetro de Ajustes).
- Criterio: por siniestro y en el reporte se ve la diferencia entre lo reclamado, lo aprobado y lo cobrado.

### RF-13 Cauciones

- Datos de la sección 4.7 y vínculo con la licitación, contrato, orden de venta o proyecto que garantiza.
- Tipo de renovación adicional **Hasta liberación**: la póliza se renueva o refactura mientras la obligación siga abierta.
- Alerta X días antes del fin de la obligación para pedir la liberación al beneficiario.
- Al pasar a Liberada (con constancia adjunta), se envía aviso al productor para cortar la refacturación.
- Criterio: un listado muestra las cauciones vigentes por beneficiario, monto garantizado y estado de la garantía.

### RF-14 Pólizas en moneda extranjera

- Póliza, cuotas y facturas en dólares (ej. seguro de transporte).
- Pago en dólares desde un diario en dólares, o en pesos al tipo de cambio de la fecha de pago; Odoo genera la diferencia de cambio al conciliar.
- En débitos en pesos, el importe se calcula con el tipo de cambio del día y queda editable si el banco aplicó otro; por eso se sugiere pago en borrador para estas pólizas.
- Reportes con importes en moneda original y en pesos.
- Criterio: una cuota de USD 1.000 pagada en pesos registra el pago al tipo de cambio de esa fecha y la diferencia de cambio contra la factura.

### RF-15 Historial de seguros por objeto

- Vehículo, empleado y bien asegurable tienen el botón inteligente **Seguros** con todas las pólizas en las que figuraron, incluidas las vencidas, renovadas y anuladas.
- La renovación y los endosos conservan el vínculo con el mismo maestro; al agregar un objeto se elige un maestro existente o se crea uno.
- El botón **Siniestros** reúne los siniestros del objeto de todas sus pólizas.
- Criterio: un vehículo asegurado tres años seguidos muestra tres pólizas en su historial, con la aseguradora y la suma asegurada de cada año, y sus siniestros.

## 7. Funcionalidades adicionales propuestas

Siniestros, cauciones, moneda extranjera e importación ya pasaron al alcance (RF-11 a RF-14) y Flota y Empleados están confirmados; el resto queda como propuesta priorizada.

| Funcionalidad | Qué resuelve | Prioridad |
| --- | --- | --- |
| Siniestros | Incorporado a la fase 1: ver RF-12. | Alta |
| Control de cuotas impagas | Alerta cuando una cuota vence sin pago: muchas aseguradoras suspenden la cobertura. Marca la póliza "con deuda". | Alta |
| Gestión de cauciones | Incorporado a la fase 1: ver RF-13. | Alta |
| Integración con Flota | Pólizas visibles desde el vehículo y alerta de vehículos activos sin póliza vigente. | Alta |
| Cotizaciones de renovación | Cargar varias ofertas (aseguradora, prima, coberturas, franquicia) antes de renovar, compararlas y elegir una; la elegida genera la póliza nueva. | Media |
| Comparativo año contra año | Costo de la póliza actual frente a la anterior por ramo y objeto, para negociar la renovación. | Media |
| Tablero de seguros | Vencimientos a 30/60/90 días, costo anual por ramo y aseguradora, cuotas del mes, siniestros abiertos. | Media |
| Distribución analítica | Imputar el costo por centro de costo, vehículo, sucursal o proyecto. | Media |
| Multimoneda | Incorporado al alcance: ver RF-14. | Media |
| Certificados de cobertura a terceros | Registro de certificados o cláusulas de no repetición pedidos por clientes, con su propio vencimiento y envío por correo. | Media |
| Nómina de asegurados | Para accidentes personales y vida: altas y bajas de empleados con endoso automático. Empleados confirmado en el cliente. | Alta |
| Importación masiva | Incorporado al alcance: ver RF-11. | Baja |
| Portal del productor | Acceso del productor para ver las pólizas que intermedia y subir documentos. | Baja |

## 8. Integración contable

El seguro se registra como un gasto pagado por adelantado que se devenga mes a mes durante la vigencia; los pagos se registran por separado según la forma de pago. Así el costo queda en el mes correcto aunque la factura llegue por el año completo.

### 8.1 Factura de la aseguradora

- Se registra como factura de proveedor con la aseguradora como proveedor y los campos Póliza, Endoso y Cuota completos.
- Una factura por póliza o una por cuota, según el modo de facturación de la póliza.
- El **método de devengamiento** es un parámetro de la póliza, con valor por defecto en Ajustes:
  - Gastos diferidos estándar (Enterprise): fecha de inicio y fin en la línea de factura y asientos mensuales automáticos de Odoo.
  - Devengamiento del módulo (Community o Enterprise): un proceso mensual genera el asiento de cada póliza en el diario de devengamiento.
  - Sin devengamiento: gasto directo en la fecha de factura, para pólizas mensuales o de bajo importe.
- En los dos primeros métodos la cuenta propuesta es Seguros a devengar (activo), con fechas iguales a la vigencia.

### 8.2 Débito automático

- En Ajustes se definen los diarios habilitados para pagar pólizas: cuentas bancarias, tarjetas de crédito y cheques. Cada cuota usa uno de ellos.
- Un proceso diario, en la fecha de vencimiento, crea el pago al proveedor por el importe de la cuota y lo concilia con la factura.
- El pago se genera en borrador o validado según la póliza; el valor por defecto se define en Ajustes.
- En tarjeta de crédito, el pago cancela la deuda con la aseguradora y la traslada al diario de la tarjeta, que se cancela al pagar el resumen.
- Al conciliar el extracto bancario, el pago ya existe y solo se empareja.

### 8.3 Pagos diferidos

- Opción A, pagos programados: al confirmar el plan, se crean los pagos con fecha futura. Quedan visibles en la deuda con proveedores y en el pronóstico de flujo de fondos.
- Opción B, cheques diferidos propios (localización argentina, `l10n_latam_check`): se emite un cheque o echeq por cuota con su fecha de pago. La deuda con el proveedor se cancela al emitir y queda la obligación en Cheques diferidos a pagar hasta la fecha de débito.
- La opción se elige por póliza; ambas dejan reflejados los importes en la contabilidad futura.

### 8.4 Asientos de ejemplo

Ejemplo ilustrativo: premio anual de 1.200.000 en 12 cuotas de 100.000, sin desglose de impuestos.

| Momento | Debe | Haber | Importe |
| --- | --- | --- | --- |
| Registro de factura | Seguros pagados por adelantado | Proveedores – Aseguradora | 1.200.000 |
| Devengamiento de cada mes | Gasto de seguros (cuenta del ramo + analítica) | Seguros pagados por adelantado | 100.000 |
| Débito automático de cada cuota | Proveedores – Aseguradora | Banco o tarjeta | 100.000 |
| Emisión de cheque diferido | Proveedores – Aseguradora | Cheques diferidos a pagar | 100.000 |
| Débito del cheque diferido | Cheques diferidos a pagar | Banco | 100.000 |
| Endoso con devolución | Proveedores – Aseguradora | Seguros pagados por adelantado (nota de crédito) | Según endoso |

Los impuestos y recargos (IVA, sellados, tasas) siguen la configuración fiscal de cada factura; el plan de cuentas definitivo lo valida el equipo contable.

### 8.5 Moneda extranjera

- La factura y las cuotas quedan en dólares; el devengamiento se registra en pesos al tipo de cambio de la factura, como hace Odoo de forma estándar.
- El pago en pesos usa el tipo de cambio de la fecha de pago y la diferencia contra la factura se registra como diferencia de cambio al conciliar.

### 8.6 Siniestros y recupero

Ejemplo ilustrativo: daño de 500.000 con franquicia de 50.000, cobrado a la empresa.

| Momento | Debe | Haber | Importe |
| --- | --- | --- | --- |
| Factura del taller por la reparación | Gasto de reparaciones | Proveedores – Taller | 500.000 |
| Aprobación del siniestro | Créditos a cobrar – Aseguradora | Recupero de siniestros | 450.000 |
| Cobro de la indemnización | Banco | Créditos a cobrar – Aseguradora | 450.000 |

La franquicia (50.000) queda como gasto neto. Si la aseguradora paga directo al taller, el crédito se compensa contra la deuda con el taller. Las tres cuentas se configuran en Ajustes y pueden variar por ramo.

**Fecha de cobro y conciliación bancaria.** El módulo lo resuelve con el asiento de aprobación. La indemnización no se factura, así que sin un asiento previo el cobro llega al banco sin nada contra qué conciliar.

- **Asiento al aprobar**: se genera en un diario Siniestros, con Debe en Siniestros a cobrar (cuenta conciliable, partner = aseguradora, vencimiento = fecha estimada de cobro, referencia = número de siniestro) y Haber en Recupero de siniestros.
- **Fecha de cobro**: la fecha estimada sale de la liquidación u orden de pago de la aseguradora. Hasta que se cobre, el crédito aparece en la antigüedad de saldos y en el flujo de fondos.
- **Conciliación**: cuando entra el movimiento bancario, un modelo de conciliación incluido en el módulo propone ese crédito por partner, importe y número de siniestro. Al conciliar, el siniestro pasa a Cobrado y guarda la fecha real de cobro.
- **Cobro menor o parcial**: si se cobra menos de lo aprobado, la diferencia se ajusta contra la cuenta de recupero, desde la conciliación o con el botón Cerrar con diferencia del siniestro. Si el cobro es parcial, el crédito queda con saldo pendiente.
- **Descuento de cuotas impagas**: si la aseguradora descuenta premio adeudado de la indemnización, se genera un asiento de compensación entre el crédito del siniestro y la deuda con la aseguradora. Solo el neto se concilia con el banco.
- **Pago directo al taller**: el asiento de compensación cancela la deuda con el taller contra el crédito a la aseguradora (dos partners distintos), sin movimiento bancario.

### 8.7 Carga inicial

- El saldo no devengado de las pólizas en curso entra con el asiento de apertura en Seguros a devengar; el módulo controla que la suma informada en las pólizas coincida con ese saldo.
- La deuda pendiente con aseguradoras entra con el saldo inicial de proveedores y se vincula a cada póliza.
- Las cuotas históricas no generan asientos.

## 9. Notificaciones, plantillas y procesos automáticos

El módulo instala siete plantillas de correo editables (`mail.template`) y un proceso diario que decide qué enviar; cada envío queda en el chatter de la póliza.

| Plantilla | Destinatarios | Cuándo se envía | Contenido mínimo |
| --- | --- | --- | --- |
| Aviso de vencimiento próximo | Responsable + usuarios a notificar (póliza y configuración) | X días antes de la fecha hasta, por cada umbral configurado | Número, ramo, aseguradora, productor, vigencia, días restantes, tipo de renovación, enlace a la póliza. |
| Póliza vencida | Responsable + usuarios a notificar | El día del vencimiento, si no está renovada | Mismos datos + aviso de que la cobertura terminó. |
| Instrucción de no renovación | Productor (CC opcional: aseguradora y responsable) | Botón No renovar (envío manual) o X días antes si la póliza tiene envío automático | Instrucción expresa de no renovar, número de póliza, ramo, vigencia, objetos asegurados, firma de la empresa. |
| Solicitud de renovación | Productor | Botón opcional, X días antes | Pedido de propuesta de renovación con los objetos actuales. |
| Cuota vencida impaga | Responsable + Contabilidad | Día siguiente al vencimiento de una cuota sin pago | Póliza, cuota, importe, riesgo de suspensión. |
| Solicitud de liberación de caución | Beneficiario o productor, con copia al responsable | X días antes del fin de la obligación garantizada | Póliza, tipo de caución, obligación garantizada, monto, pedido de constancia de liberación. |
| Siniestro sin movimiento | Responsable del siniestro | Cada X días sin cambios de estado | Siniestro, póliza, estado, importe reclamado y pendiente de cobro. |

**Procesos automáticos** (`ir.cron`, diarios):

1. Pasar a Por vencer las pólizas que entran en el umbral de aviso y enviar el aviso.
2. Pasar a Vencida, Renovada o No renovada las pólizas cuya fecha hasta ya pasó.
3. Enviar la instrucción de no renovación automática cuando corresponde.
4. Generar los pagos de débito automático del día.
5. Detectar cuotas vencidas impagas.

**Reglas comunes**: los días de aviso se definen en configuración general, en el ramo y en la póliza (prevalece el más específico); se registra cada aviso enviado para no duplicarlo; además del correo se crea una actividad para el responsable.

## 10. Vistas, menús y reportes

Una aplicación propia **Seguros** en el menú principal, con el formulario de póliza como pantalla central.

**Menús**

- Seguros › Pólizas (kanban por estado, lista, formulario, calendario por fecha hasta, pivot y gráfico).
- Seguros › Endosos · Cuotas · Siniestros · Cauciones.
- Seguros › Reportes › Vencimientos próximos · Cuotas a pagar por mes · Costo por ramo y aseguradora · Siniestros y recuperos · Cauciones por beneficiario.
- Seguros › Configuración › Ramos · Tipos de endoso · Tipos de documento · Ajustes.
- Ajustes › Seguros: parámetros de la sección 4.9 y enlaces a los ABM de configuración.

**Formulario de póliza**

- Encabezado: botones Confirmar, Renovar, No renovar, Crear factura, Generar cuotas, Nuevo endoso, Anular; barra de estados.
- Botones inteligentes: Facturas, Endosos, Cuotas, Documentos, Renovaciones, Siniestros.
- Pestañas: Objetos asegurados · Coberturas · Cuotas · Endosos · Contabilidad (cuenta, analítica, diario) · Notificaciones (días de aviso, usuarios) · Notas.
- Chatter con seguimiento de cambios en vigencia, estado, premio y tipo de renovación.

**Filtros predefinidos**: Vigentes, Vencen en 30 días, Vencidas sin renovar, Con cuotas impagas, Por ramo, Por aseguradora, Por productor.

**Reportes PDF**: Ficha de póliza (datos, objetos, endosos y cuotas) y Listado de pólizas vigentes para auditoría o para el productor.

## 11. Consideraciones técnicas para Odoo 19

Se recomienda un módulo base sin dependencias de Enterprise y módulos puente para las integraciones opcionales, así se instala en Community o Enterprise sin cambios.

**Estructura sugerida**

- `insurance_management`: modelos, vistas, seguridad, plantillas, crons, reportes.
- `insurance_management_fleet`: integración con Flota.
- `insurance_management_hr`: nómina de asegurados.
- `insurance_management_deferred`: puente con los gastos diferidos de `account_accountant` (Enterprise).
- `insurance_management_l10n_ar`: cheques diferidos propios con `l10n_latam_check`.

**Pautas de desarrollo en la versión 19**

- Restricciones de unicidad con `models.Constraint` (reemplaza a `_sql_constraints`) y validaciones con `@api.constrains`.
- Vistas con `<list>` (no `<tree>`) y visibilidad con `invisible="..."` en lugar de `attrs`.
- `group_expand` en el estado para que el kanban muestre todas las columnas.
- Secuencia por empresa para la referencia interna.
- Reglas de registro multiempresa en todos los modelos nuevos.
- Crons idempotentes: si se ejecutan dos veces el mismo día no duplican correos ni pagos.
- Montos con `Monetary` y `currency_id`; distribución analítica con `analytic.mixin`.
- Pruebas automatizadas de: validación de vigencia, renovación, endoso con diferencia de premio, generación de cuotas, débito automático y envío de alertas.

## 12. Supuestos y decisiones validadas

**Supuestos de este análisis**: la empresa opera en Argentina (terminología de productor, caución y cheques diferidos); el módulo gestiona seguros que la empresa contrata, no los que vende; una póliza tiene un solo productor y una sola aseguradora; la renovación genera una póliza nueva vinculada a la anterior.

**Decisiones validadas con el usuario clave.** Casi todas se resuelven como parámetro de Ajustes con posibilidad de cambiarlo en cada póliza (sección 4.9).

| Tema | Decisión | Dónde impacta |
| --- | --- | --- |
| Enterprise o Community | Indefinido: el método de devengamiento es un parámetro de la póliza (gastos diferidos estándar, devengamiento del módulo o sin devengamiento). | 4.1, 8.1 |
| Factura por póliza o por cuota | Depende del seguro: propiedad de la póliza. | RF-05, 8.1 |
| Débito desde banco o tarjeta | Ambos. En Ajustes se eligen los diarios habilitados para pagar pólizas. | RF-07, 8.2 |
| Pago generado en borrador o validado | Parámetro general en Ajustes, modificable en cada póliza. | RF-07, 8.2 |
| Cheques diferidos o pagos programados | Mismo comportamiento que banco y tarjeta: diario habilitado + estado del pago. | RF-07, 8.3 |
| Pólizas en dólares | Sí (ej. transporte), con gestión del tipo de cambio en el pago. | RF-14, 8.5 |
| Usuarios y días de aviso | Parámetros en Ajustes, con ajuste por ramo y por póliza. | RF-08, 4.9 |
| Correo de no renovación | Parámetro de la póliza: manual o automático. | RF-09 |
| Siniestros y cauciones | En la fase 1, con gestión y configuración contable del recupero. | RF-12, RF-13, 8.6 |
| Flota y Empleados | Ambos en uso: integraciones en la fase 1. | 4.3, 4.8 |
| Cuentas y centros de costo | Dependen de cada implementación: parámetros en Ajustes y en cada póliza. | 4.9 |
| Cuotas con vigencia que cruza el cierre | Se generan todas al confirmar; el devengamiento separa los ejercicios. | RF-07 |
| Go live con pólizas en curso | Carga indicando la cuota desde la que continúa (ej. 4/12). | RF-11, 8.7 |

**Pendientes**: volumen de pólizas a migrar y formato actual (define el alcance de la importación), y plan de cuentas definitivo para seguros y siniestros.

## 13. Plan de implementación por fases

&#91;embedded content: plan de implementación · 3 fases, 2 hitos de control\]

La fase 1 ya elimina el riesgo principal (pólizas que vencen sin aviso) y se usa en producción antes de tocar la contabilidad; cada fase arranca cuando se cumple el hito anterior. Con las decisiones de la sección 12 ya se puede estimar en horas; solo quedan pendientes el volumen de pólizas a migrar y el plan de cuentas.
