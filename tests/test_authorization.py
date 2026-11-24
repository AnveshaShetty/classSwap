from fastapi.routing import APIRoute
from starlette.routing import Mount, Route

from app.core.authorization import can_act_as_admin, can_edit_admin_chain, can_import_timetable
from app.core.csrf import require_csrf
from app.core.dependencies import get_current_user
from app.main import app
from app.models import User


def _http_routes(routes: list[object]) -> list[object]:
    result: list[object] = []
    for route in routes:
        if isinstance(route, (APIRoute, Route, Mount)):
            result.append(route)
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            result.extend(_http_routes(included_router.routes))
    return result


def _has_authenticated_dependency(dependant: object) -> bool:
    dependencies = getattr(dependant, "dependencies")
    return any(
        dependency.call is get_current_user
        or _has_authenticated_dependency(dependency)
        for dependency in dependencies
    )


def _has_dependency(dependant: object, target: object) -> bool:
    dependencies = getattr(dependant, "dependencies")
    return any(
        dependency.call is target or _has_dependency(dependency, target)
        for dependency in dependencies
    )


def test_every_route_declares_authentication_or_public_policy() -> None:
    unprotected: list[str] = []
    for route in _http_routes(app.routes):
        if isinstance(route, APIRoute):
            public = (route.openapi_extra or {}).get("x-auth-policy") == "public"
            authenticated = _has_authenticated_dependency(route.dependant)
            if public == authenticated:
                unprotected.append("%s %s" % (",".join(sorted(route.methods or [])), route.path))
        elif getattr(route, "auth_policy", None) != "public":
            unprotected.append("%s %s" % (type(route).__name__, getattr(route, "path", "")))

    assert unprotected == []


def test_every_unsafe_route_requires_csrf_validation() -> None:
    unsafe_routes = [
        route
        for route in _http_routes(app.routes)
        if isinstance(route, APIRoute)
        if route.methods.intersection({"POST", "PUT", "PATCH", "DELETE"})
    ]

    assert unsafe_routes
    assert all(_has_dependency(route.dependant, require_csrf) for route in unsafe_routes)


def test_acting_admin_permissions_are_allowlisted() -> None:
    stand_in = User(id=3, role="faculty", name="Stand-in", email="standin@example.edu", department="Physics")
    hod = User(id=2, role="hod", name="HOD", email="hod@example.edu", department="Physics")
    super_admin = User(
        id=1,
        role="super_admin",
        name="Admin",
        email="admin@example.edu",
        department="Administration",
    )

    assert can_act_as_admin(stand_in, 3, "reports")
    assert can_act_as_admin(stand_in, 3, "substitutions")
    assert not can_act_as_admin(stand_in, 3, "chain")
    assert not can_act_as_admin(stand_in, 3, "timetable")
    assert can_act_as_admin(hod, 2, "chain")
    assert not can_act_as_admin(hod, 2, "timetable")
    assert can_act_as_admin(super_admin, 99, "timetable")
    assert can_import_timetable(super_admin)
    assert not can_import_timetable(hod)
    assert can_edit_admin_chain(super_admin)
    assert not can_edit_admin_chain(hod)
