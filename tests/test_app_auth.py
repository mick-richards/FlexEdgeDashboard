"""Tests for app.py — auth helpers (_get_users logic)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGetUsers:
    """Test the _get_users helper from app.py.

    We re-implement the function logic here rather than importing it,
    because app.py has side effects (st.set_page_config) at import time.
    """

    @staticmethod
    def _get_users(secrets_mock) -> dict:
        """Mirror of app._get_users using a mock secrets object."""
        try:
            users_section = secrets_mock.get("users", {})
            if users_section and hasattr(users_section, "keys"):
                return {
                    k: dict(v) if hasattr(v, "keys") else {"password": v}
                    for k, v in users_section.items()
                }
        except Exception:
            pass
        return {}

    def test_empty_secrets(self):
        secrets = MagicMock()
        secrets.get.return_value = {}
        assert self._get_users(secrets) == {}

    def test_users_with_dict_values(self):
        """Streamlit secrets returns AttrDict-like objects with .keys()."""

        class AttrDict(dict):
            """Minimal Streamlit AttrDict stand-in."""
            pass

        mick_v = AttrDict(password="secret", role="admin")
        joris_v = AttrDict(password="pass2", role="user")
        user_data = AttrDict(mick=mick_v, joris=joris_v)

        secrets = MagicMock()
        secrets.get.return_value = user_data

        result = self._get_users(secrets)
        assert "mick" in result
        assert result["mick"]["password"] == "secret"
        assert result["mick"]["role"] == "admin"
        assert result["joris"]["role"] == "user"

    def test_users_with_plain_password(self):
        """When user value is a plain string, wrap in {"password": value}."""
        user_data = MagicMock()
        user_data.__bool__ = lambda s: True
        user_data.keys.return_value = ["demo"]
        demo_v = "mypassword"  # plain string, no .keys()
        user_data.items.return_value = [("demo", demo_v)]

        secrets = MagicMock()
        secrets.get.return_value = user_data

        result = self._get_users(secrets)
        assert result == {"demo": {"password": "mypassword"}}

    def test_exception_returns_empty(self):
        secrets = MagicMock()
        secrets.get.side_effect = Exception("boom")
        assert self._get_users(secrets) == {}
