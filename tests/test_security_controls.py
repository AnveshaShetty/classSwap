import ast
from pathlib import Path
import re

from app.services.reports import _spreadsheet_safe


APPLICATION_ROOT = Path(__file__).resolve().parents[1] / "app"
SQL_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|ALTER|DROP|CREATE)\b", re.IGNORECASE)


def _contains_sql_string(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and SQL_START.match(child.value)
        for child in ast.walk(node)
    )


def test_application_contains_no_string_built_sql() -> None:
    violations: list[str] = []
    for path in APPLICATION_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name)
                else ""
            )
            if function_name == "text" and (
                len(node.args) != 1
                or not isinstance(node.args[0], ast.Constant)
                or not isinstance(node.args[0].value, str)
            ):
                violations.append("%s:%d dynamic text()" % (path, node.lineno))
            elif function_name == "execute" and node.args and _contains_sql_string(node.args[0]):
                violations.append("%s:%d string-built execute()" % (path, node.lineno))

    assert violations == []


def test_csv_formula_prefixes_are_neutralized() -> None:
    values = (
        "=cmd|' /C calc'!A0",
        "+SUM(A1:A2)",
        "-1+2",
        "@SUM(A1)",
        "\tformula",
        "\rformula",
        " =1+1",
    )

    assert [_spreadsheet_safe(value) for value in values] == [
        "'" + value for value in values
    ]
