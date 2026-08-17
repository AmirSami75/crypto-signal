from __future__ import annotations

import os
from unittest import TestCase, mock

from crypto_signal_engine.settings import EngineSettings


class EngineSettingsTests(TestCase):
    def test_defaults_are_safe_for_an_internal_production_service(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = EngineSettings.from_environment()
        self.assertEqual("production", settings.environment)
        self.assertEqual("PAPER", settings.operating_mode)
        self.assertEqual(50051, settings.port)
        self.assertFalse(settings.enable_reflection)
        self.assertIsNone(settings.tls_certificate_path)

    def test_invalid_partial_tls_configuration_is_rejected(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"ML_TLS_CERTIFICATE_PATH": "/tmp/server.crt"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "must be set together"):
                EngineSettings.from_environment()
