from types import SimpleNamespace

from main.models.service_deployment import ServiceLayer, ServiceType
from main.utils import resolve_paths


def make(layer=ServiceLayer.STANDARD, stype=ServiceType.FLASK, project="example",
         project_root=None, deploy_root=None, overrides=None):
    return SimpleNamespace(layer=layer, service_type=stype, project=project,
                           project_root=project_root, deploy_root=deploy_root,
                           path_overrides=overrides)


def test_standard_flask_derives_from_root():
    p = resolve_paths(make(project_root="~/PRJ/example/"))
    assert p == {"app": "~/PRJ/example/app/", "data": "~/PRJ/example/data/",
                 "config": "~/PRJ/example/config/", "log": "/var/log/example/",
                 "static": None}


def test_standard_static_has_no_app():
    p = resolve_paths(make(stype=ServiceType.STATIC, project_root="~/PRJ/example/",
                           deploy_root="/var/www/example/"))
    assert p["app"] is None
    assert p["static"] == "/var/www/example/"


def test_override_beats_convention():
    p = resolve_paths(make(project_root="~/PRJ/example/",
                           overrides={"data": "~/PRJ/example/instance/"}))
    assert p["data"] == "~/PRJ/example/instance/"


def test_nonstandard_derives_nothing():
    p = resolve_paths(make(layer=ServiceLayer.NONSTANDARD, project_root="~/rss-stack/"))
    assert p == {"app": None, "static": None, "data": None, "config": None, "log": None}


def test_nonstandard_override_is_respected():
    p = resolve_paths(make(layer=ServiceLayer.NONSTANDARD,
                           overrides={"config": "~/stack/configs/"}))
    assert p["config"] == "~/stack/configs/"
