from app.image_config import PROCESSING_SETTINGS_SCHEMA, recommend_processing_settings


def test_image_configuration_only_exposes_two_user_styles() -> None:
    style_schema = PROCESSING_SETTINGS_SCHEMA["properties"]["settings"]["properties"]["style_id"]

    assert style_schema["enum"] == ["centerline", "high_detail"]
    assert recommend_processing_settings("make a closed outline")["style_id"] == "centerline"
    assert recommend_processing_settings("trace the marked color overlay")["style_id"] == "high_detail"
