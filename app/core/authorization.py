from app.models import Absence, Substitution, User


def can_access_absence(actor: User, absence: Absence, owner: User | None) -> bool:
    if actor.role == "super_admin" or actor.id == absence.faculty_id:
        return True
    return (
        owner is not None
        and actor.role == "hod"
        and actor.department == owner.department
    )


def can_access_department(actor: User, department: str) -> bool:
    return actor.role == "super_admin" or actor.department == department


def can_respond_to_substitution(actor_id: int, substitution: Substitution) -> bool:
    return actor_id == substitution.substitute_id


def can_act_as_admin(actor: User, acting_admin_id: int, permission: str) -> bool:
    if actor.role == "super_admin":
        return True
    if actor.id != acting_admin_id:
        return False
    allowed_permissions = {
        "hod": {"chain", "reports", "substitutions"},
        "faculty": {"reports", "substitutions"},
    }
    return permission in allowed_permissions.get(actor.role, set())


def can_import_timetable(actor: User) -> bool:
    return actor.role == "super_admin"


def can_edit_admin_chain(actor: User) -> bool:
    return actor.role == "super_admin"
