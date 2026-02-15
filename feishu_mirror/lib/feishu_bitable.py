from __future__ import annotations

from typing import Any

from lib.feishu_api import FeishuClient

# Feishu Bitable field type mapping
FIELD_TYPE_MAP = {
    "text": 1,
    "number": 2,
    "select": 3,
    "multi_select": 4,
    "date": 5,
    "checkbox": 7,
    "url": 15,
    "currency": 19,
}


class FeishuBitableClient:
    def __init__(self, feishu_client: FeishuClient) -> None:
        self.client = feishu_client

    def create_app(self, name: str, folder_token: str = "") -> dict[str, Any]:
        """Create a Bitable app. Returns {"app_token": ..., "url": ...}."""
        body: dict[str, Any] = {"name": name}
        if folder_token:
            body["folder_token"] = folder_token
        return self.client.request("POST", "/open-apis/bitable/v1/apps", data=body)

    def add_table(self, app_token: str, name: str, fields: list[dict]) -> dict[str, Any]:
        """Add a table to an existing Bitable app."""
        bitable_fields = [_to_bitable_field(f) for f in fields]
        return self.client.request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables",
            data={
                "table": {
                    "name": name,
                    "default_view_name": name,
                    "fields": bitable_fields,
                }
            },
        )

    def batch_create_records(
        self, app_token: str, table_id: str, records: list[dict]
    ) -> dict[str, Any]:
        """Batch write records to a Bitable table."""
        formatted = [{"fields": rec} for rec in records]
        return self.client.request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            data={"records": formatted},
        )

    def add_fields(
        self, app_token: str, table_id: str, fields: list[dict]
    ) -> list[dict[str, Any]]:
        """Add fields to an existing table. Returns list of created field info."""
        results = []
        for field in fields:
            bf = _to_bitable_field(field)
            result = self.client.request(
                "POST",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                data=bf,
            )
            results.append(result)
        return results


def _to_bitable_field(field: dict) -> dict:
    """Convert simplified field spec to Feishu Bitable field format."""
    field_type_str = field.get("type", "text")
    field_type = FIELD_TYPE_MAP.get(field_type_str, 1)
    result: dict[str, Any] = {
        "field_name": field["name"],
        "type": field_type,
    }
    # Add property config for specific types
    if field_type == 2 and "decimal_places" in field:
        result["property"] = {"formatter": f"0.{'0' * field['decimal_places']}"}
    if field_type == 5:
        result["property"] = {"date_formatter": "yyyy-MM-dd"}
    return result
