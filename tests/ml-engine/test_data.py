from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from crypto_signal.data import _get_json, load_ohlcv


class DataLoadingTests(unittest.TestCase):
    def test_external_json_request_uses_v2rayn_proxy(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status": "ok"}'
        opener = MagicMock()
        opener.open.return_value = response
        proxy_handler = object()

        with (
            patch("crypto_signal.data.urllib_request.ProxyHandler", return_value=proxy_handler) as handler,
            patch("crypto_signal.data.urllib_request.build_opener", return_value=opener) as builder,
        ):
            payload = _get_json(
                "https://example.test/data",
                {"symbol": "BTCUSDT"},
                timeout=12,
                proxy_url="http://127.0.0.1:10808",
            )

        handler.assert_called_once_with(
            {
                "http": "http://127.0.0.1:10808",
                "https": "http://127.0.0.1:10808",
            }
        )
        builder.assert_called_once_with(proxy_handler)
        opener.open.assert_called_once()
        self.assertEqual(payload, {"status": "ok"})

    def test_mixed_fractional_second_timestamps_are_accepted(self) -> None:
        csv_text = """timestamp,open,high,low,close,volume,close_time
2021-08-13 00:00:00+00:00,100,102,99,101,10,2021-08-13 00:59:59.999000+00:00
2021-08-13 01:00:00.000000+00:00,101,103,100,102,11,2021-08-13 01:59:59+00:00
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mixed_timestamps.csv"
            path.write_text(csv_text, encoding="utf-8")
            frame = load_ohlcv(path, interval="1h")

        self.assertEqual(len(frame), 2)
        self.assertEqual(str(frame["timestamp"].dtype), "datetime64[ns, UTC]")
        self.assertEqual(str(frame["close_time"].dtype), "datetime64[ns, UTC]")
        self.assertEqual(frame["close_time"].iloc[1].second, 59)


if __name__ == "__main__":
    unittest.main()
