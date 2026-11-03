# Casos de prueba manual — Gestión de seguros (Fases 1 y 2)

Guía para probar el módulo a mano en un entorno de prueba (por ejemplo,
grupolara `staging2`), de lo más simple a lo más complejo. Cada caso indica
la preparación, los pasos y el resultado esperado. Conviene hacerlos en orden:
los niveles más altos usan datos de los anteriores.

Convenciones:

- Los menús se nombran como aparecen en español: **Seguros › Pólizas ›
  Pólizas**.
- *Hoy* es el día en que se prueba. Las fechas se dan relativas a hoy para
  que los procesos automáticos tengan algo que hacer.
- **Correr un proceso a mano**: en modo desarrollador, **Ajustes › Técnico ›
  Acciones planificadas**, abrir la acción y pulsar **Ejecutar manualmente**.
  Las acciones del módulo son: *Seguros: proceso de vencimiento de pólizas*,
  *Seguros: cuotas (débitos automáticos e impagas)*, *Seguros: devengamiento
  mensual* y *Seguros: importación de pólizas*. El proceso de vencimientos
  también se corre desde **Seguros › Configuración › Ajustes › Ejecutar ahora
  el proceso de vencimientos**.
- **Correos**: en odoo.sh, las bases de staging no envían correos reales; se
  ven en **Ajustes › Técnico › Correos** (modo desarrollador) y en el chatter
  de la póliza.
- Marque cada caso con ✅ / ❌ y anote lo que vea distinto.

---

## Nivel 0 — Preparación (una sola vez)

### 0.1 Instalación y permisos
1. Verificar en **Aplicaciones** que estén instalados *Gestión de seguros*
   (19.0.2.0.0) y, si la base tiene Contabilidad Enterprise y cheques, los
   puentes *Gestión de seguros - Diferidos de Enterprise* y *Gestión de
   seguros - Cheques propios*.
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
En **Seguros › Configuración › Ajustes**, sección **Contabilidad** (solo la ve
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

### 1.3 Póliza bloqueada
En la póliza 1.1 intentar cambiar el premio, la vigencia o un objeto.

**Esperado**: los campos de contrato están en solo lectura. Responsable,
etiquetas y notas siguen editables.

### 1.4 Documentos
Pestaña **Documentos › Subir documento**, tipo *Póliza*, adjuntar un PDF.
Adjuntar otro archivo desde el chatter.

**Esperado**: los dos aparecen en la pestaña y en el botón *Documentos*; el del
chatter, resaltado hasta que se le asigna un tipo.

### 1.5 Avisos de vencimiento
1. Crear una póliza que venza dentro de 10 días, con días de aviso
   `30,15,7`, y confirmarla.
2. Correr el proceso de vencimientos.
3. Correrlo otra vez.

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
1. Correr *Seguros: cuotas (débitos automáticos e impagas)*.
2. Ver las cuotas.

**Esperado**:
- Las cuotas con vencimiento hasta hoy inclusive quedan **Pagadas**, cada
  una con un pago validado y conciliado.
- Las demás siguen *Pendiente*.
- Si se corre de nuevo, no se crean pagos nuevos.

### 2.5 Cuotas bloqueadas
Intentar cambiar el importe de una cuota facturada o pagada.

**Esperado**: no deja, y el mensaje lo explica. El medio de pago de una cuota
pendiente sí se puede cambiar.

---

## Nivel 3 — Variantes de pago, impagas y devengamiento

### 3.1 Pago en borrador para revisar
1. Nueva póliza vigente (vigencia desde hace 1 mes), medio *Débito banco
   (revisar)*, 12 cuotas, factura publicada.
2. Correr el proceso de cuotas.
3. Abrir el pago de la primera cuota.

**Esperado**: el pago está en **borrador** y la cuota, **Programada**. Al
validar el pago, la cuota pasa a *Pagada*.

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
2. Correr el proceso de cuotas.

**Esperado**:
- Las cuotas vencidas antes de hoy quedan **Vencidas**.
- La póliza muestra la cinta roja **Con deuda** y aparece en el filtro *Con
  cuotas impagas*.
- Sale **un** correo *Cuota vencida impaga* por usuario (el responsable y U3),
  en su idioma.
- En el chatter queda una nota.
- Al correrlo de nuevo, no se repite el correo.
- Al pagar la cuota, la deuda desaparece.

### 3.6 Devengamiento mensual
1. En la póliza 1.1 (vigencia desde hace 2 meses), correr *Seguros:
   devengamiento mensual*.
2. Ver la pestaña **Devengamiento** y el reporte **Seguros › Reportes › Plan de
   devengamiento**.

**Esperado**: los meses ya terminados quedan *Devengados*, con un asiento cada
uno (gasto contra seguros a devengar, con analítica si el ramo la tiene).
Correrlo otra vez no duplica asientos. Una línea no devengada se puede
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
2. Correr el devengamiento.

**Esperado**: el asiento de ese mes se registra el primer día abierto.

### 5.5 Moneda extranjera
1. Activar USD con dos cotizaciones distintas (una al inicio de la póliza y
   otra hoy).
2. Póliza en USD, premio USD 1.200, 12 cuotas, medio *Débito banco*, factura
   publicada.
3. Correr el proceso de cuotas.

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
   actual.
2. Póliza con vigencia desde hace 3 meses, 12 cuotas. En **Contabilidad ›
   Carga inicial**: *Póliza en curso*, continúa desde la cuota 4, importe a
   devengar 900.000. Confirmar.
3. **Generar cuotas**, **Crear factura** y publicarla.
4. **Generar devengamiento inicial**.

**Esperado**:
- Las cuotas 1 a 3 quedan *Pagadas* (históricas, sin pagos ni asientos).
- La factura es solo por las cuotas 4 a 12 y no genera devengamiento
  propio.
- El devengamiento inicial reparte 900.000 desde el mes de la puesta en
  marcha hasta el fin.
- Un segundo intento de generar el devengamiento inicial da error.

### 6.2 Control de saldo de apertura
1. Ver Ajustes › Contabilidad: *A devengar en pólizas en curso* = 900.000 y
   diferencia −900.000.
2. Registrar un asiento de apertura con fecha anterior a la puesta en marcha:
   debe *Seguros a devengar* 900.000.

**Esperado**: la diferencia de apertura pasa a 0.

### 6.3 Factura de apertura
Publicar una factura de la aseguradora (deuda previa) y, ya publicada, cargarle
la **Póliza de seguros** de 6.1.

**Esperado**: la póliza muestra la factura en el botón *Facturas* con su
saldo.

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

## Registro de resultados

| Caso | Fecha | Quién | Resultado | Observaciones |
| --- | --- | --- | --- | --- |
| | | | | |
