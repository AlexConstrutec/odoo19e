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

# NOTA IMPORTANTE, leer antes de confiar el Informe del Empleador a estos códigos:
# estos dos catálogos y sus códigos numéricos son una PRIMERA APROXIMACIÓN construida
# a partir de las categorías oficiales de pueblo/comunidad lingüística de Guatemala
# (Ley de Idiomas Nacionales, Decreto 19-2003, y las categorías de auto-identificación
# étnica ya usadas en formularios de censo/MITRAB) - los CÓDIGOS NUMÉRICOS (no las
# etiquetas) NO se verificaron contra el catálogo oficial exacto que MITRAB espera en
# el archivo del Informe del Empleador. Antes de esta pasada, el wizard mandaba
# SIEMPRE '1' (Pueblo de pertenencia) y '10' (Comunidad Lingüística) para TODOS los
# empleados, sin importar la realidad de cada quien - así que cualquier código real
# aquí, aunque no esté 100% confirmado contra el catálogo oficial, ya es una mejora
# real sobre el estado anterior. Verificar los códigos numéricos con el catálogo
# oficial de MITRAB antes de confiar un filing real en ellos.
PUEBLO_PERTENENCIA = [
    ('1', 'Maya'),
    ('2', 'Garífuna'),
    ('3', 'Xinka'),
    ('4', 'Ladino / Mestizo'),
    ('5', 'Extranjero'),
    ('6', 'Otro'),
]

COMUNIDAD_LINGUISTICA = [
    ('1', 'Achi'), ('2', 'Akateko'), ('3', 'Awakateko'), ('4', 'Chalchiteko'), ('5', 'Chorti'),
    ('6', 'Chuj'), ('7', 'Itza'), ('8', "Ixil"), ('9', "Jakalteko (Popti')"), ('10', 'Español'),
    ('11', "Kaqchikel"), ('12', "K'iche'"), ('13', "Mam"), ('14', "Mopan"), ('15', "Poqomam"),
    ('16', "Poqomchi'"), ('17', "Q'anjob'al"), ('18', "Q'eqchi'"), ('19', "Sakapulteko"),
    ('20', "Sipakapense"), ('21', "Tektiteko"), ('22', "Tz'utujil"), ('23', "Uspanteko"),
    ('24', 'Garífuna (idioma)'), ('25', 'Xinka (idioma)'),
]
