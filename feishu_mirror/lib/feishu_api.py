from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


BASE_URL = "https://open.feishu.cn"


@dataclass
class FeishuAuth:
    app_id: str
    app_secret: str


class FeishuApiError(RuntimeError):
    pass


class FeishuClient:
    def __init__(
        self,
        auth: FeishuAuth,
        *,
        page_size: int = 200,
        retry_max: int = 5,
        retry_backoff_ms: int = 800,
    ) -> None:
        self.auth = auth
        self.page_size = page_size
        self.retry_max = retry_max
        self.retry_backoff_ms = retry_backoff_ms
        self._tenant_token: str | None = None
        self._tenant_token_expiry: float = 0.0

    def _get_token(self) -> str:
        now = time.time()
        if self._tenant_token and now < self._tenant_token_expiry - 120:
            return self._tenant_token

        resp = requests.post(
            f"{BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.auth.app_id, "app_secret": self.auth.app_secret},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise FeishuApiError(f"token error: {payload.get('msg')}")

        self._tenant_token = payload["tenant_access_token"]
        self._tenant_token_expiry = now + int(payload.get("expire", 7200))
        return self._tenant_token

    def _do_request(self, method: str, path: str, *, headers: dict, timeout: int, **kwargs) -> dict:
        """Shared retry loop for both JSON and raw (multipart) requests."""
        for attempt in range(self.retry_max):
            resp = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=timeout, **kwargs)

            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt + 1 >= self.retry_max:
                    break
                time.sleep((self.retry_backoff_ms * (2**attempt)) / 1000.0)
                continue

            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                raise FeishuApiError(f"{path}: {payload.get('msg')} ({payload.get('code')})")
            return payload.get("data", {})

        raise FeishuApiError(f"request failed after retries: {path}")

    def request(self, method: str, path: str, *, params: dict | None = None, data: dict | None = None) -> dict:
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        return self._do_request(method, path, headers=headers, timeout=30, params=params, json=data)

    def _request_raw(self, method: str, path: str, *, params: dict | None = None, files: dict | None = None, data: dict | None = None) -> dict:
        """Non-JSON request (e.g. multipart/form-data for image upload)."""
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        return self._do_request(method, path, headers=headers, timeout=60, params=params, files=files, data=data)

    def upload_image(self, image_bytes: bytes, image_type: str = "message") -> str:
        """Upload image to Feishu, return image_key."""
        import io
        data = self._request_raw(
            "POST",
            "/open-apis/im/v1/images",
            files={"image": ("chart.png", io.BytesIO(image_bytes), "image/png")},
            data={"image_type": image_type},
        )
        return data["image_key"]

    def send_image_message(
        self,
        receive_id: str,
        image_key: str,
        receive_id_type: str = "chat_id",
    ) -> dict:
        """Send image message to a Feishu chat or user.
        receive_id_type: 'chat_id' for group chats, 'open_id' for DMs.
        """
        import json as _json
        return self.request(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            data={
                "receive_id": receive_id,
                "msg_type": "image",
                "content": _json.dumps({"image_key": image_key}),
            },
        )

    def send_card_message(
        self,
        receive_id: str,
        card: dict,
        receive_id_type: str = "open_id",
    ) -> dict:
        """Send interactive card message to a Feishu chat or user."""
        import json as _json
        return self.request(
            "POST",
            "/open-apis/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            data={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": _json.dumps(card),
            },
        )

    def list_app_visible_users(self, app_id: str) -> list[str]:
        """Return open_ids of all users in the app's contact scope.
        Paginates through /open-apis/contact/v3/scopes.
        Falls back to empty list on permission errors.
        """
        open_ids: list[str] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"user_id_type": "open_id", "page_size": 100}
            if page_token:
                params["page_token"] = page_token
            try:
                data = self.request("GET", "/open-apis/contact/v3/scopes", params=params)
            except Exception:
                break
            for uid in data.get("user_ids", []):
                if uid not in open_ids:
                    open_ids.append(uid)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
        return open_ids

    def list_space_nodes(self, space_id: str, page_token: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": min(self.page_size, 200)}
        if page_token:
            params["page_token"] = page_token
        return self.request("GET", f"/open-apis/wiki/v2/spaces/{space_id}/nodes", params=params)

    def get_doc_raw_content(self, doc_token: str) -> dict[str, Any]:
        return self.request("GET", f"/open-apis/docx/v1/documents/{doc_token}/raw_content")

    def get_doc_meta(self, doc_token: str) -> dict[str, Any]:
        return self.request("GET", f"/open-apis/docx/v1/documents/{doc_token}")

    def list_drive_files(self, folder_token: str, page_token: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "folder_token": folder_token,
            "page_size": min(self.page_size, 200),
        }
        if page_token:
            params["page_token"] = page_token
        return self.request("GET", "/open-apis/drive/v1/files", params=params)
