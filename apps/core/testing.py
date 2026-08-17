"""Ayudantes compartidos por la suite de tests (T4.1).

`login_as` estaba copiado **33 veces**, 24 de ellas byte a byte, y las nueve
variantes sólo agregaban grupos, pertenencia a un tenant, o devolvían también el
usuario. Cada copia es una oportunidad de que el montaje de permisos de un test
diverja del de los demás sin que nadie lo note -- y el montaje de permisos es
justo lo que estos tests están afirmando.

No es un `conftest.py` con fixtures, que era lo que proponía la fila del plan.
Un ayudante importable deduplica lo mismo **sin tocar la firma de cada función de
test**: adoptarlo cuesta cambiar dos líneas por archivo en vez de trescientas
firmas, y una migración grande de tests que se hace a mano es exactamente donde
se cuela el error que la suite ya no puede cazar, porque la suite es lo que se
está moviendo. Las fixtures de datos (`two_tenant_world`) siguen pendientes y se
harán cuando haya un segundo lector real que las pida.
"""

from django.contrib.auth.models import Group, Permission, User
from django.test import Client


def login_as(*codenames, groups=(), member_of=None):
    """Un cliente autenticado con **exactamente** estos permisos.

    El nombre de usuario se deriva de los permisos, así que dos clientes con
    permisos distintos no chocan en la restricción de unicidad y el que falla se
    identifica solo en el error.

    `groups` agrega grupos por nombre (el destinatario de las notificaciones,
    por ejemplo). `member_of` agrega el usuario a un `OperationalTenant`, que es
    como `visible_tenant_ids` resuelve el alcance -- una M2M `members`, no un
    campo del perfil.

    El usuario queda en `client.user`: los tests que lo necesitaban devolvían
    una tupla, y una tupla obliga a desempaquetar en todos los que no lo
    necesitan.
    """
    # `nosec B106`: es la contraseña de un usuario que sólo existe dentro de una
    # base de datos de test que se destruye al terminar. Bandit no marcaba esto
    # cuando el ayudante vivía copiado en archivos `test_*.py` (excluidos del
    # análisis); al extraerlo a un módulo normal, sí — y la respuesta correcta es
    # justificar la excepción acá, no ampliar la exclusión a todo el módulo.
    user = User.objects.create_user(  # nosec B106
        f"u-{'-'.join(codenames) or 'none'}", password="pw"
    )
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    if member_of is not None:
        member_of.members.add(user)
    client = Client()
    assert client.login(username=user.username, password="pw")  # nosec B106
    client.user = user
    return client
