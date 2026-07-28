from main.models.service_deployment import ServiceDeployment, ServiceLayer


def test_model_has_new_fields_and_not_old():
    cols = {c.name for c in ServiceDeployment.__table__.columns}
    assert {"layer", "project_root", "deploy_root", "workspace_url", "path_overrides"} <= cols
    assert not ({"app_path", "static_path", "data_path", "log_path", "config_path"} & cols)


def test_layer_enum_values():
    assert ServiceLayer.STANDARD.value == "standard"
    assert ServiceLayer.NONSTANDARD.value == "nonstandard"
