# Casos de prueba manual — Gestión de seguros (Fases 1, 2 y 3)

Guía para probar el módulo a mano en un entorno de prueba (por ejemplo,
grupolara `staging2`), de lo más simple a lo más complejo. Cada caso indica
la preparación, los pasos y el resultado esperado. Conviene hacerlos en orden:
los niveles más altos usan datos de los anteriores.

Convenciones:

- Los menús se nombran como aparecen en español: **Seguros › Pólizas ›
  Pólizas**.
- *Hoy* es el día en que se prueba. Las fechas se dan relativas a hoy para
  que los procesos automáticos tengan algo que hacer.
- **Ejecutar un proceso automático a mano**: los procesos automáticos son
  *acciones planificadas* que Odoo corre solo todos los días. Para no esperar,
  se ejecutan a mano así:
  1. Activar el **modo desarrollador** (Ajustes › al pie, *Activar el modo de
     desarrollador*).
  2. Ir a **Ajustes › Técnico › Automatización › Acciones planificadas**.
  3. Buscar la acción por su nombre, abrirla y pulsar **Ejecutar de forma
     manual** (según el idioma, *Ejecutar manualmente*).

  | En los casos dice… | Nombre de la acción planificada |
  | --- | --- |
  | proceso de vencimientos | Seguros: proceso de vencimiento de pólizas |
  | proceso de cuotas | Seguros: cuotas (débitos automáticos e impagas) |
  | proceso de devengamiento | Seguros: devengamiento mensual |
  | proceso de importación | Seguros: importación de pólizas |
  | proceso de siniestros | Seguros: siniestros sin movimiento |

  El proceso de vencimientos también se ejecuta desde **Seguros ›
  Configuración › Ajustes › Ejecutar ahora el proceso de vencimientos**.
- **Correos**: en odoo.sh, las bases de staging no envían correos reales; se
  ven en **Ajustes › Técnico › Correos** (modo desarrollador) y en el chatter
  de la póliza.
- Al final de cada caso, marque el resultado y anote lo que vea distinto.

---

## Nivel 0 — Preparación (una sola vez)

### 0.1 Instalación y permisos
1. Verificar en **Aplicaciones** que estén instalados *Gestión de seguros*
   (19.0.3.0.0) y, si la base tiene Contabilidad Enterprise, cheques y los
   pagos de adhoc, los puentes *Gestión de seguros - Diferidos de
   Enterprise*, *Gestión de seguros - Cheques propios* y *Gestión de
   seguros - Pagos de adhoc*. Con Flota, Empleados, Ventas y Proyectos
   instalados, también *Gestión de seguros - Flota*, *- Empleados*,
   *- Ventas* y *- Proyectos* (se instalan solos al actualizar).
2. Crear (o elegir) tres usuarios de prueba:
   - **U1**: Seguros / Usuario, sin permisos de Contabilidad.
   - **U2**: Seguros / Administrador.
   - **U3**: Seguros / Usuario + Contabilidad / Facturación.
3. Su usuario de prueba: Seguros / Administrador + Contabilidad /
   Administrador.

**Esperado**: aparece el menú **Seguros** para los cuatro; U1 no ve
**Configuración**.

### 0.2 Contactos
1. Crear la aseguradora *Aseguradora Prueba SA* (empresa, con CUIT y correo)
   y marcar **Es aseguradora** (pestaña Ventas y compras, grupo Seguros).
2. Crear el productor *Productor Prueba* con correo y marcar **Es productor
   de seguros**.

**Esperado**: los filtros *Aseguradoras* y *Productores* de Contactos los
muestran.

### 0.3 Configuración contable
Antes, el contador crea las cuentas, diarios, impuestos y el producto que
indica el artículo **Parametrización contable** de la guía (dentro de *Puesta
en marcha*). Después, en **Seguros › Configuración › Ajustes**, sección **Contabilidad** (solo la ve
un administrador de Contabilidad):
1. **Producto de seguros**: crear un producto de servicio *Prima de seguros*
   con IVA compras 21% y una cuenta de gasto de seguros.
2. **Modo de facturación**: Una factura por póliza.
3. **Método de devengamiento**: Devengamiento del módulo.
4. **Cuenta de seguros a devengar**: una cuenta de activo corriente (crearla si
   no existe).
5. **Diario de devengamiento**: Operaciones varias.
6. Guardar.

### 0.4 Medios de pago
En **Seguros › Configuración › Medios de pago** crear:

| Nombre | Tipo | Diario | Estado de los pagos |
| --- | --- | --- | --- |
| Débito banco | Débito automático | Banco | Validado |
| Débito banco (revisar) | Débito automático | Banco | Borrador |
| Transferencia programada | Transferencia programada | Banco | Borrador |
| Manual | Manual | — | — |
| Cheque diferido (si está el puente) | Cheque diferido | Banco con *Cheques propios* | Borrador |

Después, en Ajustes › **Pagos**: medio por defecto *Débito banco*, y en
*Usuarios de contabilidad a notificar* agregar a U3.

**Esperado**: si el método de pago del diario no tiene cuenta de pagos
pendientes, el medio de pago no se guarda y lo explica.

---

## Nivel 1 — Póliza básica (Fase 1)

### 1.1 Crear y confirmar una póliza
1. **Seguros › Pólizas › Pólizas › Nuevo**: ramo *Automotor*, aseguradora y
   productor de prueba, vigencia desde hace 2 meses hasta dentro de 10 meses,
   prima 1.000.000, premio 1.210.000.
2. Agregar dos objetos: *Camioneta* (patente AB123CD, suma 20.000.000) y
   *Auto* (patente AC456EF, suma 10.000.000).
3. Guardar sin número de póliza y pulsar **Confirmar**.
4. Cargar el número *PRUEBA-001* y **Confirmar**.

**Esperado**: el paso 3 pide el número de póliza. Tras el 4, el estado es
*Vigente*, la referencia *SEG/AAAA/NNNN* y la suma asegurada total es
30.000.000.

### 1.2 Validaciones
1. Nueva póliza con fecha hasta anterior a la fecha desde → error.
2. Nueva póliza de 18 meses → con el control en *Bloquear* no confirma; con
   *Advertencia* confirma y deja nota en el chatter.
3. Otra póliza con el mismo número, aseguradora y fecha desde → error de
   duplicado.

### 1.2a Prima o premio en cero
1. Nueva póliza completa pero con prima y premio en 0. **Confirmar**.
2. Pulsar **Volver**; cargar el premio y dejar la prima en 0. **Confirmar**.
3. Pulsar **Confirmar igual**.

**Esperado**: en los pasos 1 y 2 aparece la advertencia *Prima o premio en
cero* con la póliza y sus importes; **Volver** no confirma nada. En el paso 3
la póliza se confirma y el historial dice *Confirmada con la prima y/o el
premio en cero*. Con prima y premio cargados, Confirmar no muestra nada.

### 1.2b Póliza que empieza más adelante
1. Nueva póliza con vigencia desde dentro de 2 días hasta dentro de 32 días
   (días de aviso `30`), con un objeto. Confirmar.
2. Ejecutar a mano el proceso de vencimientos.

**Esperado**: la póliza queda **Por iniciar** (no Vigente ni Por vencer),
*Cubierta hoy* = No, no figura en el filtro *Vigentes* y el proceso no envía
avisos. Se le puede agregar un endoso. El día de su fecha desde pasa a *Por vencer* y recién ahí recibe el aviso.

### 1.3 Póliza bloqueada
En la póliza 1.1 intentar cambiar el premio, la vigencia o un objeto.

**Esperado**: los campos de contrato están en solo lectura. Responsable,
etiquetas y notas siguen editables.

### 1.3b Bien asegurable
1. **Seguros › Pólizas › Bienes asegurables › Nuevo**: *Depósito central*,
   tipo Inmueble, valor de referencia 50.000.000.
2. En una póliza en borrador, agregar un objeto y elegir solo el bien
   asegurable.
3. Agregar otro objeto escribiendo primero descripción y suma, y después
   eligiendo el bien.
4. Confirmar la póliza y abrir el bien asegurable.

**Esperado**: en el paso 2 se completan la descripción *Depósito central* y
la suma 50.000.000; en el 3 se respeta lo escrito. El bien muestra el botón
**Pólizas (1)** y la pestaña **Historial de seguros** con la póliza, su
estado, las fechas y la suma.

### 1.4 Documentos
Pestaña **Documentos › Subir documento**, tipo *Póliza*, adjuntar un PDF.
Adjuntar otro archivo desde el chatter.

**Esperado**: los dos aparecen en la pestaña y en el botón *Documentos*; el del
chatter, resaltado hasta que se le asigna un tipo.

### 1.5 Avisos de vencimiento
1. Crear una póliza que venza dentro de 10 días, con días de aviso
   `30,15,7`, y confirmarla.
2. Ejecutar a mano el proceso de vencimientos.
3. Ejecutarlo otra vez.

**Esperado**: la póliza pasa a *Por vencer*. Sale **un solo** aviso (umbral
15) y queda una actividad para el responsable. La segunda corrida no envía
nada nuevo.

### 1.6 Renovar y no renovar
1. En la póliza de 1.5, **Renovar**: se crea un borrador con los mismos
   objetos y la vigencia siguiente, vinculado a la original.
2. En otra póliza vigente, **No renovar** con un motivo, enviando la
   instrucción al productor.

**Esperado**: la instrucción queda en el chatter con la fecha de envío; la
póliza sigue vigente hasta su fecha hasta.

---

## Nivel 2 — Cuotas, factura y pago simple

### 2.1 Generar cuotas
1. En la póliza 1.1, pestaña **Cuotas › Generar cuotas**.
2. Revisar lo que propone: 12 cuotas, primer vencimiento igual a la fecha
   desde, total 1.210.000, medio *Débito banco*.
3. **Generar**.

**Esperado**: 12 cuotas de 100.833,33; la última, 100.833,37. *Total de
cuotas* 1.210.000 y *Diferencia con las cuotas* 0.

### 2.2 Editar cuotas (prorrateo)
1. Cambiar la cuota 1 a 150.000.
2. Ver la diferencia (−49.166,67, en rojo).
3. Volver a dejarla en 100.833,33.

**Esperado**: la diferencia se actualiza y vuelve a 0.

### 2.3 Crear y publicar la factura
1. **Crear factura**.
2. En la factura borrador: proveedor la aseguradora, una línea con el
   producto de seguros por 1.000.000 + IVA 21%, botón **Póliza**. Completar
   fecha y número de comprobante.
3. **Confirmar** (publicar).

**Esperado**:
- La factura tiene 12 vencimientos (pestaña Apuntes contables), uno por cuota.
- La línea va a *Seguros a devengar*.
- En la póliza, el botón *Facturas 1* muestra el saldo adeudado.
- Cada cuota muestra la factura.
- La pestaña **Devengamiento** tiene 12 meses de 83.333,33 (la prima neta).

### 2.4 Débito automático
1. Ejecutar a mano el proceso de cuotas (acción planificada *Seguros: cuotas
   (débitos automáticos e impagas)*, ver *Convenciones*). Alternativa: en la
   pestaña Cuotas de la póliza, **Generar pagos**.
2. Ver las cuotas.

**Esperado**:
- Las cuotas con vencimiento hasta hoy inclusive quedan **Pagadas**, cada
  una con un pago validado y conciliado.
- Las demás siguen *Pendiente*.
- Si se corre de nuevo, no se crean pagos nuevos; **Generar pagos** avisa
  que los débitos que todavía no vencen se pagan en su fecha.

### 2.5 Cuotas bloqueadas
Intentar cambiar el importe de una cuota facturada o pagada.

**Esperado**: no deja, y el mensaje lo explica. El medio de pago de una cuota
pendiente sí se puede cambiar.

---

## Nivel 3 — Variantes de pago, impagas y devengamiento

### 3.1 Pago en borrador para revisar
1. Nueva póliza vigente (vigencia desde hace 1 mes), medio *Débito banco
   (revisar)*, 12 cuotas, factura publicada.
2. Ejecutar a mano el proceso de cuotas.
3. Abrir el pago de la primera cuota.

**Esperado**: el pago está en **borrador** y la cuota, **Programada**. El
pago no tiene campos de seguros; en la pestaña *Deudas* figura solo el
vencimiento de la cuota 1 de esa factura (no las demás deudas con la
aseguradora) y el importe a pagar es el de la cuota. Al validar el pago, la
cuota pasa a *Pagada* y el pago muestra *1 Factura*; las otras facturas de la
aseguradora siguen impagas.

### 3.2 Transferencia programada
1. Póliza con medio *Transferencia programada* y factura publicada.

**Esperado**: al publicar la factura se crea un pago por cuota, fechado en cada
vencimiento. Todas las cuotas quedan *Programadas*. Aparecen en Contabilidad
como pagos futuros.

### 3.3 Cheque diferido (con el puente)
1. Póliza con medio *Cheque diferido* y factura publicada.
2. Abrir un pago, cargar el número de cheque y validarlo.

**Esperado**: cada pago tiene un cheque propio con fecha de pago igual al
vencimiento de su cuota. Al validarlo, la cuota queda pagada.

### 3.4 Pago manual desde la factura
1. Póliza con medio *Manual*, factura publicada.
2. Desde la factura, **Pagar** solo el importe de la primera cuota.

**Esperado**: la primera cuota pasa a *Pagada* y la factura queda en pago
parcial. El proceso automático nunca paga cuotas manuales.

### 3.5 Cuota vencida impaga
1. Póliza con medio *Manual*, vigencia desde hace 2 meses, 12 cuotas, factura
   publicada.
2. Ejecutar a mano el proceso de cuotas.

**Esperado**:
- Las cuotas vencidas antes de hoy quedan **Vencidas**.
- La póliza muestra la cinta roja **Con deuda** y aparece en el filtro *Con
  cuotas impagas*.
- Sale **un** correo *Cuota vencida impaga* por usuario (el responsable y U3),
  en su idioma.
- En el chatter queda una nota.
- Al ejecutarlo de nuevo, no se repite el correo.
- Al pagar la cuota, la deuda desaparece.

### 3.6 Devengamiento mensual
1. En la póliza 1.1 (vigencia desde hace 2 meses), ejecutar a mano *Seguros:
   devengamiento mensual*.
2. Ver la pestaña **Devengamiento** y el reporte **Seguros › Reportes › Plan de
   devengamiento**.

**Esperado**: los meses ya terminados quedan *Devengados*, con un asiento cada
uno (gasto contra seguros a devengar, con analítica si el ramo la tiene).
Ejecutarlo otra vez no duplica asientos. Una línea no devengada se puede
editar; una devengada, no.

### 3.7 Una factura por cuota
1. En otra póliza, pestaña **Contabilidad**, modo *Una factura por cuota*.
2. Generar cuotas y **Crear factura**.

**Esperado**: se crea una factura por cuota, cada una con su vencimiento.

### 3.8 Sin devengamiento
Póliza con método *Sin devengamiento (gasto directo)*: la factura va directo a
la cuenta de gasto y no aparece la pestaña Devengamiento.

---

## Nivel 4 — Endosos

### 4.1 Alta de objeto con premio adicional
1. En la póliza 1.1, **Nuevo endoso**, tipo *Alta de objeto*, vigencia hoy,
   un objeto nuevo *Utilitario*, diferencia de premio 60.000. Confirmar.
2. En el endoso: **Generar cuotas** y **Crear factura**; publicar la factura.

**Esperado**:
- El objeto aparece en la póliza con fecha de alta y el endoso.
- El premio total con endosos sube 60.000.
- Las cuotas del endoso se llaman *POL/E01 1/n* y van desde hoy hasta el fin.
- La factura queda vinculada al endoso.
- El devengamiento del endoso empieza en el mes del endoso.

### 4.2 Baja de objeto con devolución
1. **Nuevo endoso**, tipo *Baja de objeto*, objeto *Auto*, motivo *Vendido*,
   diferencia −50.000, devolución *Descontar de las próximas cuotas*.
   Confirmar.
2. **Crear nota de crédito** y publicarla.

**Esperado**:
- El objeto queda dado de baja (gris), con fecha y motivo, y la suma
  asegurada total baja.
- La nota de crédito se concilia con la(s) próxima(s) cuota(s) pendiente(s),
  que bajan su saldo pendiente.
- El plan de devengamiento suma un devengamiento negativo.

### 4.3 Prórroga y cambio de datos
1. Endoso *Prórroga de vigencia* con nueva fecha hasta un mes después.
2. Endoso *Cambio de datos* con otro productor.

**Esperado**: la póliza toma la nueva fecha hasta y el nuevo productor; ambos
endosos quedan en la pestaña Endosos.

### 4.4 Anulación
1. En una póliza con cuotas sin facturar, endoso *Anulación* con fecha hoy.

**Esperado**: la póliza pasa a *Anulada*, las cuotas no facturadas a *Anulada*
y los meses de devengamiento posteriores se juntan en el mes de la anulación.

---

## Nivel 5 — Correcciones y casos borde

### 5.1 Factura a borrador y vuelta a publicar
1. Tomar una factura publicada con alguna cuota pagada y sin meses devengados.
2. **Restablecer a borrador**, corregir el importe de la línea y publicar.

**Esperado**:
- Las cuotas se vuelven a vincular.
- El pago ya hecho se concilia de nuevo; si el importe cambió, queda parcial.
- No se generan pagos duplicados.
- El plan de devengamiento se rearma con el nuevo importe.

### 5.2 Cancelar una factura
1. Factura publicada **sin** meses devengados: restablecer a borrador y
   **Cancelar**.
2. Factura publicada **con** algún mes devengado: restablecer a borrador e
   intentar **Cancelar**.

**Esperado**:
- En el caso 1, las cuotas quedan libres: se pueden editar y facturar de
  nuevo, y el plan desaparece.
- En el caso 2, no deja cancelar y pide una nota de crédito.

### 5.3 Volver una póliza a borrador
Con U2, **Volver a borrador** una póliza con factura publicada.

**Esperado**: no deja. En una póliza confirmada sin facturas, sí.

### 5.4 Período cerrado
1. Fijar una fecha de bloqueo contable posterior al fin de un mes pendiente
   de devengar.
2. Ejecutar a mano el proceso de devengamiento.

**Esperado**: el asiento de ese mes se registra el primer día abierto.

### 5.5 Moneda extranjera
1. Activar USD con dos cotizaciones distintas (una al inicio de la póliza y
   otra hoy).
2. Póliza en USD, premio USD 1.200, 12 cuotas, medio *Débito banco*, factura
   publicada.
3. Ejecutar a mano el proceso de cuotas.

**Esperado**:
- Las cuotas y la factura están en USD.
- El devengamiento se calcula en pesos al tipo de cambio de la factura.
- El débito sale del banco en pesos al tipo de cambio del día y, al
  conciliar, se genera el asiento de diferencia de cambio.
- **Cuotas por mes** suma en pesos; **Costo por ramo y aseguradora** muestra
  pesos y USD.

---

## Nivel 6 — Carga inicial e importación

### 6.1 Póliza en curso a mano
1. En Ajustes › Contabilidad, **Fecha de puesta en marcha** = el día 1 del mes
   actual, **Cuenta transitoria de apertura** y (opcional) **Diario de deuda
   de apertura** (compras, sin documentos).
2. Póliza con vigencia desde hace 3 meses, 12 cuotas, prima 1.000.000 y
   premio 1.200.000. En **Contabilidad › Carga inicial**: *Póliza en curso*,
   continúa desde la cuota 4, *Facturada al inicio (deuda de apertura)*.
   Confirmar.
3. **Generar cuotas**, **Crear factura** y publicarla.
4. **Generar devengamiento inicial**.
5. Cambiar el importe a devengar a 450.000 y volver a pulsar **Generar
   devengamiento inicial**.

**Esperado**:
- Al poner continúa desde la cuota 4 y generar las cuotas, el importe a
  devengar sugerido es 750.000 (la prima, sin impuestos, de las cuotas 4 a
  12).
- Las cuotas 1 a 3 quedan *Pagadas* (históricas, sin pagos ni asientos).
- **Crear factura** arma una sola *factura de deuda de apertura* por 900.000
  (el premio de las cuotas 4 a 12): fecha = día anterior a la puesta en
  marcha, cuenta transitoria de apertura, **sin impuestos**, diario de deuda
  de apertura si está cargado, campo *Deuda de apertura de seguros*
  marcado. Al publicarla tiene un vencimiento por cuota, no genera
  devengamiento y no aparece en el reporte de costo.
- El devengamiento inicial reparte el importe a devengar desde el mes de la
  puesta en marcha hasta el fin (pestaña Devengamiento) y aparece un aviso
  con los meses y el total. Las cuotas no cambian.
- Sin la cuenta transitoria en los ajustes, **Crear factura** da un error que
  pide cargarla.
- El segundo intento reemplaza el plan por 450.000 (no lo suma). Una vez que
  un mes está devengado, ya no se puede regenerar.

### 6.1b Póliza en curso que se factura por cuota
1. Igual que 6.1, pero en *Carga inicial* elegir *Se factura por cuota en
   Odoo*.
2. **Generar cuotas**, **Crear factura** y publicarla.

**Esperado**:
- El importe a devengar sugerido es 0.
- La factura es normal: producto de seguros, impuestos, cuenta Seguros a
  devengar, sin la marca de deuda de apertura.
- Genera su devengamiento desde el mes de la puesta en marcha hasta el fin
  (no antes).

### 6.1a Póliza marcada en curso después de generar las cuotas
1. Póliza confirmada con 12 cuotas generadas, sin facturar, con la fecha de
   puesta en marcha anterior a la cuota 3 (o vacía).
2. En **Contabilidad › Carga inicial**: marcar *Póliza en curso*,
   continúa desde la cuota 4. Guardar.
3. Cambiar continúa desde la cuota a 3. Guardar.
4. **Crear factura** y publicarla. Cambiar continúa desde la cuota a 5.
5. Pasar la factura a borrador, cancelarla y volver a poner 5.
6. Desmarcar *Póliza en curso*. Guardar.

**Esperado**:
- Paso 2: las cuotas 1 a 3 pasan a *Pagadas* (columna *Histórica*
  marcada) al guardar, y queda nota en el historial.
- Paso 3: la cuota 3 vuelve a *Pendiente* (o *Vencida impaga*); 1 y 2
  siguen históricas. Si la cuota 3 vence antes de la puesta en marcha, sigue
  histórica.
- Paso 4: error, la cuota 4 ya está facturada. Nada cambia.
- Paso 5: las cuotas 1 a 4 quedan históricas.
- Paso 6: ninguna cuota queda histórica.

### 6.2 Control de saldo de apertura
1. Ver Ajustes › Contabilidad: *A devengar en pólizas en curso* = 750.000 y
   diferencia −750.000.
2. Registrar un asiento de apertura con fecha anterior a la puesta en marcha:
   debe *Seguros a devengar* 750.000, debe una cuenta de patrimonio 150.000
   (el IVA ya tomado, en este ejemplo), haber *Transitoria de apertura*
   900.000.

**Esperado**:
- La diferencia de apertura pasa a 0.
- Con la factura de deuda de apertura de 6.1 publicada, la cuenta
  *Transitoria de apertura* queda en 0.

### 6.3 Factura del sistema anterior vinculada
Publicar una factura de la aseguradora con fecha anterior a la puesta en
marcha y, ya publicada, cargarle la **Póliza de seguro** de 6.1b.

**Esperado**: la póliza muestra la factura en el botón *Facturas* con su
saldo, y la factura no genera devengamiento (lo anterior a la puesta en
marcha se devenga con el importe a devengar).

### 6.4 Importación desde Excel
1. **Seguros › Configuración › Importar pólizas en curso › Nuevo › Descargar
   plantilla**.
2. Completar:
   - Hoja **Pólizas**: 3 filas. Una correcta en curso (continúa desde 4, con
     importe a devengar), una correcta normal y una con un ramo que no existe.
   - Hoja **Objetos**: dos objetos para la primera póliza.
   - Hoja **Cuotas**: en la segunda póliza, la cuota 1 con otro importe.
3. Subir el archivo, **Leer archivo** y **Procesar ahora**.
4. Corregir el ramo en el Excel, subirlo de nuevo, **Leer archivo** y
   **Procesar ahora**.
5. Crear otra importación con el mismo archivo y procesarla.

**Esperado**:
- Paso 3: dos líneas *Importada* y una *Error* que dice que el ramo no
  existe. Las pólizas importadas tienen sus objetos y cuotas (históricas en
  la primera, con el importe de la hoja Cuotas en la segunda) y el
  devengamiento inicial.
- Paso 4: solo se reemplaza la línea con error, que pasa a *Importada*.
- Paso 5: todas las líneas quedan *Ya importada*, sin cambios en las pólizas.

---

## Nivel 7 — Permisos, idioma e integraciones

### 7.1 Usuario sin Contabilidad (U1)
Con U1, abrir una póliza facturada.

**Esperado**:
- Ve las cuotas, sus estados y saldos, y el botón de Facturas no aparece.
- No ve las columnas Factura/Pago, la pestaña Devengamiento ni las cuentas.
- Puede generar cuotas.
- El reporte *Costo por ramo y aseguradora* abre sin errores y sin la
  columna Factura.

### 7.2 Ocultar costos
1. En Ajustes, activar **Ocultar costos a los usuarios**.
2. Con U1, abrir pólizas, endosos, cuotas, el PDF y el correo de cuota impaga.

**Esperado**:
- U1 no ve importes en ninguna parte: premios, sumas, cuotas, endosos,
  reportes.
- El correo de cuota impaga le llega sin importe.

### 7.3 Ajustes contables
Con U2 (sin Contabilidad), abrir Ajustes.

**Esperado**: no ve la sección Contabilidad; puede guardar lo demás.

### 7.4 Idioma
Con un usuario en inglés como responsable y U3 en español, repetir 3.5.

**Esperado**:
- Cada uno recibe el correo en su idioma.
- Los asientos de devengamiento del proceso automático se ven en el idioma
  de la compañía.

### 7.5 Diferidos de Enterprise (con el puente)
1. En Contabilidad › Ajustes, configurar la cuenta de gastos diferidos.
2. En una póliza, método *Gastos diferidos de Enterprise*.
3. Facturar y publicar.

**Esperado**:
- La línea de la factura lleva las fechas de diferimiento de la vigencia.
- Contabilidad genera los asientos de diferimiento.
- No hay plan de devengamiento del módulo.

### 7.6 Localización argentina (grupolara)
1. Factura A de la aseguradora con número de comprobante.
2. Débito automático validado.

**Esperado**:
- Sale una orden de pago con su talonario, conciliada con la cuota.
- Si la compañía tiene retenciones configuradas, el pago las aplica y la
  cuota igual queda pagada. *Este punto no se pudo probar localmente.*

---

## Nivel 8 — Siniestros, cauciones e integraciones (Fase 3)

### 8.0 Configuración de siniestros
Antes, el contador crea el diario y las cuentas del punto 9 de
**Parametrización contable**. En **Seguros › Configuración › Ajustes**:
1. Sección **Contabilidad de siniestros**: diario *Siniestros* (varios),
   cuenta *Siniestros a cobrar* (tipo A cobrar), *Recupero de siniestros* y
   *Pérdida por ejecución de cauciones*.
2. Sección **Siniestros y cauciones**: *Siniestros sin movimiento* = 30,
   *Pedir la liberación* = 30, envío *Manual*.

**Esperado**: la cuenta de siniestros a cobrar solo acepta cuentas de tipo A
cobrar.

### 8.1 Siniestro cobrado a la empresa
1. En una póliza de automotor vigente, **Nuevo siniestro**: objeto afectado,
   tipo *Daño propio*, efecto *Sin efecto*, destino *Cobro a la empresa*,
   daño 500.000, franquicia 50.000, reclamado 500.000.
2. **Denunciar a la aseguradora**, cargar el número de la aseguradora,
   **En análisis**.
3. Cargar aprobado 450.000 y fecha estimada de cobro; **Aprobar** (con U3 o
   su usuario).
4. Abrir **Asientos contables** del siniestro.
5. **Registrar cobro** por 450.000 en el banco.

**Esperado**:
- El asiento de aprobación debita *Siniestros a cobrar* (aseguradora,
  vencimiento = fecha estimada) y acredita *Recupero*; su referencia es
  `SIN/... - <número de la aseguradora>`.
- Antes del cobro, el crédito aparece en la antigüedad de saldos de la
  aseguradora.
- Al cobrar, el siniestro pasa solo a **Cobrado**, con fecha de cobro;
  *Reclamado menos cobrado* = 50.000. **Cerrar** lo pasa a *Cerrado*.

### 8.2 Cobro desde la conciliación bancaria (Enterprise)
1. Otro siniestro aprobado por 300.000 (sin registrar el cobro).
2. Cargar en el extracto del banco una línea de 300.000 con el concepto
   "TRANSF SINIESTRO <número de la aseguradora>".

**Esperado**: la conciliación bancaria propone el crédito del siniestro; al
conciliar, el siniestro pasa a *Cobrado*.

### 8.3 Cobro parcial y cierre con diferencia
1. Siniestro aprobado por 200.000; **Registrar cobro** por 150.000.
2. **Cerrar con diferencia**.

**Esperado**: tras el cobro sigue *Aprobado* con 50.000 pendientes; al cerrar
se genera un asiento contra *Recupero* por 50.000 y el siniestro queda
*Cerrado*.

### 8.4 Compensaciones
1. Siniestro con destino *Pago directo al taller*, taller cargado, aprobado
   por 450.000. Cargar la factura del taller por 500.000.
2. **Compensar** › *Pago directo al taller*, elegir la factura, **Compensar**.
3. En otra póliza de la misma aseguradora con una cuota impaga (pago en
   borrador), siniestro aprobado; **Compensar** › *Premio impago*, elegir el
   vencimiento de la cuota.

**Esperado**: la factura del taller queda con 50.000 pendientes y el
siniestro *Cobrado*; la cuota compensada queda *Pagada* y su pago en borrador
*Cancelado*, el siniestro sigue aprobado por la diferencia.

### 8.5 Pérdida total y reemplazo
1. Póliza de automotor con un solo vehículo y cuotas sin facturar. Siniestro
   tipo *Robo*, efecto *Pérdida total del objeto*, aprobado.
2. **Dar de baja el objeto** y confirmar el endoso.
3. **Asegurar reemplazo**.

**Esperado**: el objeto queda dado de baja con el siniestro como motivo; sin
objetos, la póliza pasa a *Anulada* con el motivo *Pérdida total por el
siniestro…*, las cuotas no facturadas a *Anulada* y el devengamiento se cierra;
el reemplazo abre una póliza nueva en borrador copiada (sin objetos). Con dos
vehículos, la póliza sigue vigente y el reemplazo es un endoso de alta.

### 8.6 Suma reducida y rehabilitación
1. Póliza de incendio vigente; siniestro efecto *Reduce la suma asegurada*,
   aprobado por 300.000.
2. En la póliza, mostrar la columna opcional *Suma disponible* de los objetos.
3. **Rehabilitar la suma asegurada** en el siniestro y confirmar el endoso.

**Esperado**: la suma disponible baja 300.000 y vuelve a la suma asegurada
al confirmar el endoso.

### 8.7 Siniestro sin movimiento
1. Bajar el ajuste *Siniestros sin movimiento* a 1 día y denunciar un
   siniestro.
2. Al día siguiente, ejecutar el **proceso de siniestros**.

**Esperado**: el responsable recibe un correo (en Correos) y queda una nota
en el chatter; al ejecutarlo otra vez el mismo día no se repite.

### 8.8 Caución hasta liberación
1. Póliza en el ramo *Caución*, tipo de renovación **Hasta liberación**,
   pestaña **Caución**: beneficiario con correo, tipo *Cumplimiento de
   contrato*, obligación, monto garantizado, fin de la obligación = hoy + 20
   días. Vigencia que terminó ayer. Confirmar.
2. **Entregada al beneficiario**.
3. Ejecutar el **proceso de vencimientos**.
4. **Liberar** sin documento; luego cargar un documento tipo *Constancia de
   liberación de caución* y **Liberar**.
5. **Devuelta a la aseguradora**.

**Esperado**:
- La póliza no pasa a *Vencida*: queda *Por vencer*, con un aviso y una
  actividad para renovar o liberar, y una actividad para pedir la liberación
  (fin de la obligación dentro de 30 días).
- Liberar sin constancia da error; con constancia la garantía pasa a
  *Liberada*, se abre el correo al productor y la póliza termina como *No
  renovada*.
- **Seguros › Pólizas › Cauciones** y **Reportes › Cauciones por
  beneficiario** la muestran con su monto garantizado.

### 8.9 Ejecución de caución
1. Otra caución vigente con cuotas sin facturar. **Nuevo siniestro** (tipo
   *Ejecución de caución*), aprobado por lo que pagó la aseguradora.

**Esperado**: el asiento debita *Pérdida por ejecución de cauciones* y
acredita la cuenta a pagar de la aseguradora; la garantía pasa a *Ejecutada*
y la póliza a *Anulada*; *Cancelar aprobación* no está permitido.

### 8.10 Flota
1. En Flota, dos vehículos con patentes `AB 123 CD` y `XY999ZZ`.
2. Póliza de automotor con objetos de patente `ab-123cd` y `XY 999 ZZ`.
3. Abrir el vehículo: botones **Seguros** y **Siniestros**.
4. En Flota, filtro **Sin seguro vigente**.
5. En el ramo *Automotor*, marcar **Requiere vehículo de flota** y confirmar
   una póliza con un objeto de patente inexistente.

**Esperado**: los objetos quedan vinculados a sus vehículos; el vehículo
dice *Asegurado* y lista la póliza; el filtro muestra los vehículos sin
póliza vigente; la póliza con patente inexistente no se confirma. Los
objetos cargados antes de actualizar quedaron vinculados solos.

### 8.11 Empleados, ventas y proyectos
1. Póliza de *Accidentes personales* con objetos que eligen empleados.
2. Caución con *Orden de venta garantizada* y otra con *Proyecto
   garantizado*.

**Esperado**: el empleado muestra sus botones **Seguros** y **Siniestros**;
la orden de venta y el proyecto muestran el botón **Cauciones**.

### 8.12 Tablero y permisos
1. **Seguros › Tablero** con su usuario y con U1.
2. Con U1 (sin Contabilidad), intentar **Aprobar** un siniestro con importe
   aprobado.

**Esperado**: cada número abre sus registros; U1 no ve importes si *Ocultar
costos* está activo; U1 no puede aprobar con asiento (mensaje de permisos),
sí puede aprobar uno sin importe.

---

## Registro de resultados

| Caso | Fecha | Quién | Resultado | Observaciones |
| --- | --- | --- | --- | --- |
| | | | | |
