NIVEL_ACADEMICO = [
    ('other', 'Ninguno'),
    ('2', 'Primaria Incompleta'),
    ('3', 'Primaria Completa'),
    ('4', 'Básico Incompleto'),
    ('5', 'Básico Completo'),
    ('6', 'Diversificado Incompleto'),
    ('graduate', 'Diversificado Completo'),
    ('8', 'Estudiante Universitario'),
    ('9', 'Técnico Universitario'),
    ('bachelor', 'Licenciatura'),
    ('11', 'Postgrado'),
    ('master', 'Maestría'),
    ('doctor', 'Doctorado'),
]

DISCAPACIDAD = [
    ('1', 'Ninguna'),
    ('2', 'Discapacidad auditiva'),
    ('3', 'Discapacidad visual'),
    ('4', 'Discapacidad múltiple'),
    ('5', 'Discapacidad física o motora'),
    ('6', 'Discapacidad intelectual'),
    ('7', 'Otra'),
]

# VERIFICADO 2026-09-17 - fuente: "Formato_Informe Empleados.xlsx", el archivo real
# descargado por el usuario DIRECTAMENTE del sistema electrónico de MITRAB
# (informeynomina2989.mintrabajo.gob.gt). Ese Excel trae, además de la hoja
# "Empleados", una hoja de catálogo por cada campo codificado (con validación de
# datos apuntando a ellas) - "Pueblo_pertenencia" y "Comunidad_lingüistica" entre
# ellas. Los códigos de abajo son una transcripción exacta de esas dos hojas -
# reemplazan dos intentos previos sin esta fuente (uno basado en Decreto 19-2003 sin
# catálogo numérico, otro basado en un catálogo de 27 códigos que usa ZOLIC para un
# trámite distinto - ninguno de los dos coincide con lo que MITRAB realmente pide).
PUEBLO_PERTENENCIA = [
    ('1', 'Maya'),
    ('2', 'Garífuna'),
    ('3', 'Xinka'),
    ('4', 'Afrodescendiente / creole / afromestizo'),
    ('5', 'Ladino'),
    ('6', 'Extranjero'),
]

# Solo cubre los 22 idiomas mayas (código 99 = "No aplica", para quien no hable
# ninguno - NO hay código propio para español/garífuna/xinka/idioma extranjero en
# este catálogo, a diferencia de lo que se había asumido antes de ver el archivo
# real). DEBE quedar idéntico, código por código, a la copia de Community
# (construtec_account_payment_order_19/models/hr_employee.py) - el write() de ese
# módulo empuja el NÚMERO, no la etiqueta, así que un desfase entre los dos catálogos
# corrompería el dato en silencio al sincronizar.
COMUNIDAD_LINGUISTICA = [
    ('1', "Achi'"), ('2', 'Akateka'), ('3', 'Awakateka'), ('4', "Ch'orti'"),
    ('5', 'Chalchiteka'), ('6', 'Chuj'), ('7', "Itza'"), ('8', 'Ixil'), ('9', 'Jakalteka'),
    ('10', "K'iche'"), ('11', 'Kaqchikel'), ('12', 'Mam'), ('13', 'Mopan'), ('14', 'Poqomam'),
    ('15', "Poqomchi'"), ('16', "Q'anjob'al"), ('17', "Q'eqchi'"), ('18', 'Sakapulteka'),
    ('19', 'Sipakapense'), ('20', 'Tektiteka'), ('21', "Tz'utujil"), ('22', 'Uspanteka'),
    ('99', 'No aplica'),
]
