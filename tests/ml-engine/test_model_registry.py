"""Which model answers for a requested pair, and what happens when the obvious one cannot.

The engine used to serve one artifact and reject every symbol but its own. Serving arbitrary pairs turns
that single check into a resolution order, and every step of it has a failure that looks like success:

* **A pooled model applied to the wrong interval.** Every feature is measured in candle counts, so a 1h
  estimator asked about 4h candles still returns three numbers that sum to 1 and still looks confident.
  Nothing downstream can detect it, so the interval has to be part of every lookup key and part of every
  filename — including the pooled one.
* **A broken override taking the symbol down with it.** A per-symbol model is an optimisation over the
  pooled one, not a precondition for serving the symbol, so its failure must fall through rather than
  refuse.
* **An inventory that lists artifacts which cannot serve.** "No model for SOLUSDT" and "the mount is
  empty" and "your filename has a hyphen in it" are the same message unless the refusal carries what it
  found and why each thing was skipped.
* **A legacy artifact served as a barrier model.** It has no take-profit inputs, so the mismatch would
  otherwise surface as a shape error inside `predict_proba` on the first real request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from crypto_signal.labeling import BARRIER_FEATURE_COLUMNS
from crypto_signal_engine.application.errors import ModelUnavailable
from crypto_signal_engine.infrastructure.model_registry import (
    WILDCARD_SYMBOL,
    Candidate,
    ModelRegistry,
    parse_artifact_name,
)


def bundle(
    symbols: tuple[str, ...],
    interval: str,
    *,
    barrier: bool = True,
    reach: bool = True,
    atr_window: int = 14,
    max_horizon: int = 24,
) -> dict:
    """A minimal artifact in the shape the registry reads.

    `barrier=False` produces the legacy close-to-close shape — an estimator with no take-profit inputs —
    which is the artifact currently deployed and the one the barrier check exists to catch.
    """
    columns = ("log_return_1", "rsi_14") + (BARRIER_FEATURE_COLUMNS if barrier else ())
    frame = pd.DataFrame(
        np.random.default_rng(7).normal(size=(90, len(columns))), columns=list(columns)
    )
    estimator = HistGradientBoostingClassifier(max_iter=5, random_state=0)
    estimator.fit(frame, np.tile([-1, 0, 1], 30))
    metadata = {
        "trained_at_utc": datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat(),
        "symbols": list(symbols),
        "interval": interval,
        "atr_window": atr_window,
        "max_horizon": max_horizon,
        "project_version": "0.4.0",
    }
    if reach:
        metadata["calibration"] = {
            "reach": {
                "ceiling": 0.688,
                "maximum": 0.814,
                "attainment": {"0.50": 0.2812, "0.60": 0.1342, "0.70": 0.0055, "0.75": 0.0004},
            }
        }
    return {"model": estimator, "feature_columns": list(columns), "metadata": metadata}


class ArtifactNameTests(unittest.TestCase):
    def test_a_symbol_and_an_interval_are_read_from_the_filename(self) -> None:
        parsed = parse_artifact_name(Path("BTCUSDT_1h.joblib"))
        self.assertEqual((parsed.symbol, parsed.interval), ("BTCUSDT", "1h"))
        self.assertFalse(parsed.is_pooled)
        self.assertTrue(parsed.names_its_identity)

    def test_the_pooled_entry_carries_an_interval_like_every_other(self) -> None:
        """`_pooled.joblib` is refused on purpose: a pooled model is not interval-agnostic.

        Accepting it would mean either loading the artifact to discover which interval it answers for —
        defeating the point of a filename-only scan — or letting one pooled entry answer for every
        interval, which is the bug that cannot be detected downstream.
        """
        parsed = parse_artifact_name(Path("_pooled_1h.joblib"))
        self.assertEqual((parsed.symbol, parsed.interval), (WILDCARD_SYMBOL, "1h"))
        self.assertTrue(parsed.is_pooled)
        self.assertIsNone(parse_artifact_name(Path("_pooled.joblib")))

    def test_minutes_and_months_are_not_the_same_interval(self) -> None:
        """Binance spells a minute `1m` and a month `1M`, so the parse cannot normalise case."""
        self.assertEqual(parse_artifact_name(Path("BTCUSDT_1m.joblib")).interval, "1m")
        self.assertEqual(parse_artifact_name(Path("BTCUSDT_1M.joblib")).interval, "1M")

    def test_a_name_that_is_not_an_artifact_is_not_guessed_at(self) -> None:
        for name in (
            "btcusdt-1h.joblib",  # hyphen instead of underscore
            "model.joblib",  # no identity at all
            "BTC_USDT_1h.joblib",  # no venue symbol contains an underscore
            "BTCUSDT_0h.joblib",  # zero candles is not an interval
            "BTCUSDT_1y.joblib",  # not a venue interval unit
            "BTCUSDT_1h.pkl",  # not a joblib bundle
        ):
            with self.subTest(name=name):
                self.assertIsNone(parse_artifact_name(Path(name)))


class RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.directory = Path(self._temporary.name)

    def write(self, name: str, payload: dict) -> Path:
        path = self.directory / name
        joblib.dump(payload, path)
        return path

    def registry(self, single: Path | None = None) -> ModelRegistry:
        return ModelRegistry(self.directory, single_artifact=single)


class ResolutionTests(RegistryTestCase):
    def test_a_dedicated_model_is_preferred_over_the_pooled_one(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        self.write("_pooled_1h.joblib", bundle(("ETHUSDT", "BNBUSDT"), "1h"))
        resolved = self.registry().resolve("BTCUSDT", "1h").descriptor
        self.assertEqual(resolved.model_id, "BTCUSDT:1h")
        self.assertFalse(resolved.is_pooled)

    def test_the_pooled_model_answers_for_a_symbol_it_never_saw(self) -> None:
        """The reason pooling is viable: every feature is scale-free, so no pair is special."""
        self.write("_pooled_1h.joblib", bundle(("BTCUSDT", "ETHUSDT"), "1h"))
        resolved = self.registry().resolve("DOGEUSDT", "1h").descriptor
        self.assertEqual(resolved.model_id, f"{WILDCARD_SYMBOL}:1h")
        self.assertTrue(resolved.covers("DOGEUSDT"))

    def test_the_pooled_model_does_not_answer_for_another_interval(self) -> None:
        """The failure nothing downstream could catch: 1h features applied to 4h candles.

        `momentum_24` is a day of 1h candles and four days of 4h ones. The estimator accepts the row
        either way and returns a confident-looking triple, so the guard has to be structural — the
        interval is part of the lookup key, never inferred.
        """
        self.write("_pooled_1h.joblib", bundle(("BTCUSDT",), "1h"))
        with self.assertRaises(ModelUnavailable) as raised:
            self.registry().resolve("BTCUSDT", "4h")
        self.assertIn("4h", str(raised.exception))

    def test_a_symbol_is_matched_regardless_of_how_the_caller_cased_it(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        registry = self.registry()
        self.assertEqual(registry.resolve(" btcusdt ", "1h").descriptor.model_id, "BTCUSDT:1h")

    def test_the_serving_assumptions_travel_with_the_model(self) -> None:
        """Barrier distances arrive as percentages and are divided by ATR to reach training units.

        Computing that ATR over a different window than the labeller used rescales every barrier input,
        and the model then answers a question nobody asked — so the window is not a serving preference,
        it is part of the artifact.
        """
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h", atr_window=20, max_horizon=36))
        resolved = self.registry().resolve("BTCUSDT", "1h").descriptor
        self.assertEqual(resolved.atr_window, 20)
        self.assertEqual(resolved.max_horizon, 36)


class FallthroughTests(RegistryTestCase):
    """An override is an optimisation, so its failure must not deny what the pooled model can serve."""

    def test_an_unloadable_override_falls_through_to_the_pooled_model(self) -> None:
        (self.directory / "SOLUSDT_1h.joblib").write_bytes(b"truncated")
        self.write("_pooled_1h.joblib", bundle(("BTCUSDT",), "1h"))
        registry = self.registry()
        self.assertEqual(registry.resolve("SOLUSDT", "1h").descriptor.model_id, f"{WILDCARD_SYMBOL}:1h")
        self.assertIn("SOLUSDT_1h.joblib", registry.rejections())

    def test_an_override_trained_on_another_pair_is_refused_as_an_override(self) -> None:
        """Serving it would attribute one pair's model to another under the requested symbol's name."""
        self.write("XRPUSDT_1h.joblib", bundle(("ETHUSDT",), "1h"))
        self.write("_pooled_1h.joblib", bundle(("BTCUSDT",), "1h"))
        registry = self.registry()
        self.assertEqual(registry.resolve("XRPUSDT", "1h").descriptor.model_id, f"{WILDCARD_SYMBOL}:1h")
        self.assertIn("trained on ETHUSDT", registry.rejections()["XRPUSDT_1h.joblib"])

    def test_a_legacy_artifact_is_refused_at_load_rather_than_at_prediction(self) -> None:
        """The deployed close-to-close model has no take-profit inputs.

        Without this check the mismatch surfaces as a feature-count error inside `predict_proba` on the
        first real request, and the caller sees an internal error instead of "this artifact answers a
        different question".
        """
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h", barrier=False))
        registry = self.registry()
        with self.assertRaises(ModelUnavailable):
            registry.resolve("BTCUSDT", "1h")
        reason = registry.rejections()["BTCUSDT_1h.joblib"]
        self.assertIn("barrier inputs", reason)
        for column in BARRIER_FEATURE_COLUMNS:
            self.assertIn(column, reason)

    def test_a_bundle_whose_interval_contradicts_its_filename_is_refused(self) -> None:
        self.write("BTCUSDT_15m.joblib", bundle(("BTCUSDT",), "1h"))
        registry = self.registry()
        with self.assertRaises(ModelUnavailable):
            registry.resolve("BTCUSDT", "15m")
        self.assertIn("candle counts", registry.rejections()["BTCUSDT_15m.joblib"])


class InventoryTests(RegistryTestCase):
    """A refusal has to distinguish 'no model for this pair' from 'your filename has a typo'."""

    def test_the_refusal_lists_what_can_serve_and_explains_what_cannot(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        self.write("SOLUSDT_1h.joblib", bundle(("SOLUSDT",), "1h", barrier=False))
        (self.directory / "btcusdt-1h.joblib").write_bytes(b"not a bundle")
        registry = self.registry()
        registry.available()

        with self.assertRaises(ModelUnavailable) as raised:
            registry.resolve("DOGEUSDT", "1d")
        message = str(raised.exception)
        available, _, skipped = message.partition("Skipped:")
        self.assertIn("BTCUSDT 1h", available)
        self.assertNotIn("SOLUSDT 1h", available)
        self.assertIn("SOLUSDT_1h.joblib", skipped)
        self.assertIn("btcusdt-1h.joblib", message)
        self.assertIn("expected <SYMBOL>_<INTERVAL>", message)

    def test_a_verdict_reached_by_loading_survives_the_next_scan(self) -> None:
        """The bug this catches: rebuilding the skip list from filenames on every request.

        Only a load can discover that an artifact carries no barrier inputs. Recomputing the list from
        the directory listing would discard that on the next request, leaving the inventory advertising
        a model that cannot answer.
        """
        self.write("SOLUSDT_1h.joblib", bundle(("SOLUSDT",), "1h", barrier=False))
        registry = self.registry()
        registry.available()
        self.assertIn("SOLUSDT_1h.joblib", registry.rejections())
        registry.scan()
        self.assertIn("SOLUSDT_1h.joblib", registry.rejections())

    def test_a_verdict_about_a_deleted_file_is_dropped(self) -> None:
        path = self.write("SOLUSDT_1h.joblib", bundle(("SOLUSDT",), "1h", barrier=False))
        registry = self.registry()
        registry.available()
        path.unlink()
        registry.scan()
        self.assertNotIn("SOLUSDT_1h.joblib", registry.rejections())

    def test_an_empty_directory_says_so(self) -> None:
        with self.assertRaises(ModelUnavailable) as raised:
            self.registry().resolve("BTCUSDT", "1h")
        self.assertIn("no usable artifacts", str(raised.exception))

    def test_capabilities_advertise_only_what_can_actually_answer(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        self.write("_pooled_4h.joblib", bundle(("BTCUSDT", "ETHUSDT"), "4h"))
        self.write("SOLUSDT_1h.joblib", bundle(("SOLUSDT",), "1h", barrier=False))
        registry = self.registry()
        self.assertEqual(
            sorted(descriptor.model_id for descriptor in registry.available()),
            ["BTCUSDT:1h", f"{WILDCARD_SYMBOL}:4h"],
        )
        self.assertIn("SOLUSDT_1h.joblib", registry.rejections())


class CachingTests(RegistryTestCase):
    def test_an_unchanged_artifact_is_loaded_once(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        registry = self.registry()
        self.assertIs(registry.resolve("BTCUSDT", "1h"), registry.resolve("BTCUSDT", "1h"))

    def test_replacing_the_file_on_the_mount_is_picked_up(self) -> None:
        """Artifacts arrive on a mounted volume, so a swap must not need a restart."""
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h", max_horizon=24))
        registry = self.registry()
        first = registry.resolve("BTCUSDT", "1h").descriptor
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h", max_horizon=48))
        second = registry.resolve("BTCUSDT", "1h").descriptor
        self.assertEqual(second.max_horizon, 48)
        self.assertNotEqual(first.model_version, second.model_version)

    def test_the_version_is_the_artifact_digest(self) -> None:
        """Two engines serving the same file report the same version, and a no-op rebuild is not new."""
        payload = bundle(("BTCUSDT",), "1h")
        self.write("BTCUSDT_1h.joblib", payload)
        self.write("_pooled_1h.joblib", payload)
        registry = self.registry()
        exact = registry.resolve("BTCUSDT", "1h").descriptor
        pooled = registry.resolve("DOGEUSDT", "1h").descriptor
        self.assertEqual(exact.model_version, pooled.model_version)
        self.assertEqual(len(exact.model_version), 64)

    def test_each_model_gets_its_own_inference_lock(self) -> None:
        """Serialising access per estimator is worth keeping; serialising across symbols is not."""
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        self.write("_pooled_1h.joblib", bundle(("ETHUSDT",), "1h"))
        registry = self.registry()
        first = registry.resolve("BTCUSDT", "1h")
        second = registry.resolve("DOGEUSDT", "1h")
        self.assertIsNot(first._lock, second._lock)


class StandaloneArtifactTests(RegistryTestCase):
    """`ML_MODEL_PATH` is the migration path off the one-model deployment."""

    def test_a_file_outside_the_naming_convention_resolves_from_its_metadata(self) -> None:
        """Safe for exactly one file. Doing it for a directory means opening every artifact to scan."""
        with tempfile.TemporaryDirectory() as elsewhere:
            path = Path(elsewhere) / "model.joblib"
            joblib.dump(bundle(("BTCUSDT",), "1h"), path)
            resolved = self.registry(single=path).resolve("BTCUSDT", "1h").descriptor
            self.assertEqual(resolved.model_id, "BTCUSDT:1h")
            self.assertFalse(resolved.is_pooled)

    def test_a_standalone_trained_on_several_pairs_answers_for_all_of_them(self) -> None:
        """No filename to declare intent, so it is read from the training set."""
        with tempfile.TemporaryDirectory() as elsewhere:
            path = Path(elsewhere) / "model.joblib"
            joblib.dump(bundle(("BTCUSDT", "ETHUSDT", "BNBUSDT"), "1h"), path)
            resolved = self.registry(single=path).resolve("DOGEUSDT", "1h").descriptor
            self.assertTrue(resolved.is_pooled)
            self.assertEqual(resolved.model_id, f"{WILDCARD_SYMBOL}:1h")

    def test_a_single_symbol_standalone_makes_no_claim_beyond_its_pair(self) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            path = Path(elsewhere) / "model.joblib"
            joblib.dump(bundle(("BTCUSDT",), "1h"), path)
            with self.assertRaises(ModelUnavailable):
                self.registry(single=path).resolve("DOGEUSDT", "1h")

    def test_the_directory_is_consulted_before_the_standalone(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h", max_horizon=24))
        with tempfile.TemporaryDirectory() as elsewhere:
            path = Path(elsewhere) / "model.joblib"
            joblib.dump(bundle(("BTCUSDT",), "1h", max_horizon=48), path)
            resolved = self.registry(single=path).resolve("BTCUSDT", "1h").descriptor
            self.assertEqual(resolved.max_horizon, 24, "the directory model wins")

    def test_a_broken_standalone_is_reported_rather_than_raised(self) -> None:
        """It is the fallback: when a directory model answered, its breakage is not the caller's problem."""
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        with tempfile.TemporaryDirectory() as elsewhere:
            path = Path(elsewhere) / "model.joblib"
            path.write_bytes(b"truncated")
            registry = self.registry(single=path)
            self.assertEqual(registry.resolve("BTCUSDT", "1h").descriptor.model_id, "BTCUSDT:1h")
            with self.assertRaises(ModelUnavailable):
                registry.resolve("DOGEUSDT", "1h")
            self.assertIn("model.joblib", registry.rejections())


class ConfidenceReachTests(RegistryTestCase):
    """A confidence floor above what the model reaches produces silence, not safety."""

    def test_a_measured_ceiling_travels_with_the_model(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        descriptor = self.registry().resolve("BTCUSDT", "1h").descriptor
        self.assertAlmostEqual(descriptor.confidence_ceiling, 0.688, places=6)
        self.assertTrue(descriptor.is_reachable(0.60))
        self.assertFalse(descriptor.is_reachable(0.75))

    def test_a_floor_between_measured_points_reads_the_level_below_it(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        descriptor = self.registry().resolve("BTCUSDT", "1h").descriptor
        self.assertTrue(descriptor.is_reachable(0.65), "0.60's 13.4% is the best available evidence")
        self.assertFalse(descriptor.is_reachable(0.99))

    def test_an_unmeasured_model_does_not_refuse_every_threshold(self) -> None:
        """Refusing on the grounds that nobody checked is a worse failure than an unenforced check."""
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h", reach=False))
        descriptor = self.registry().resolve("BTCUSDT", "1h").descriptor
        self.assertIsNone(descriptor.confidence_ceiling)
        self.assertTrue(descriptor.is_reachable(0.95))


class InferenceTests(RegistryTestCase):
    def test_a_resolved_model_predicts_through_its_lock(self) -> None:
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        model = self.registry().resolve("BTCUSDT", "1h")
        row = pd.DataFrame(
            [[0.0] * model.descriptor.feature_count], columns=list(model.descriptor.feature_columns)
        )
        probabilities = model.predict_proba(row)
        self.assertEqual(probabilities.shape, (1, 3))
        self.assertAlmostEqual(float(probabilities.sum()), 1.0, places=9)

    def test_the_feature_order_the_model_expects_is_published(self) -> None:
        """Serving builds its row from this, so a mismatch is a silent reordering of inputs."""
        self.write("BTCUSDT_1h.joblib", bundle(("BTCUSDT",), "1h"))
        columns = self.registry().resolve("BTCUSDT", "1h").descriptor.feature_columns
        self.assertEqual(columns[-len(BARRIER_FEATURE_COLUMNS):], BARRIER_FEATURE_COLUMNS)


if __name__ == "__main__":
    unittest.main()
