from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates


TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIRECTORY)),
        autoescape=True,
    )
)
