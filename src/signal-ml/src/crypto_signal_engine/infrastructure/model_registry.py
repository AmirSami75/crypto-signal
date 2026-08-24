"""Resolution from a requested `(symbol, interval)` to the model that may answer for it.

The engine used to serve exactly one artifact and reject every request that did not match its symbol.
That is the wrong shape for the two capabilities this platform exists to provide: a caller asking for a
signal on an arbitrary USDT pair, and a bot configured on one. Since every feature is scale-free — log
returns, ratios, z-scores, nothing carrying an absolute price — one estimator trained on pooled pairs
generalises to a pair it never saw, so the useful default is a pooled model with per-symbol overrides
where a symbol has earned one.

**Resolution is exact match, then pooled, then refusal that lists what is available.** The refusal
carries the inventory because "no model for SOLUSDT 1h" and "no models at all, the mount is empty" are
the same message otherwise, and they call for opposite actions.

**A pooled model is not interval-agnostic, and this is the trap the layout is built to avoid.** Every
feature is measured in *candle counts* — `momentum_24` is a day on 1h candles and four days on 4h ones —
so an estimator trained on 1h has no meaning applied to 4h, even though the numbers all arrive in range
and `predict_proba` returns something confident-looking. So the interval is part of the filename,
including for the pooled entry: `_pooled_1h.joblib`, not `_pooled.joblib`. One parse rule covers both
kinds of file, a directory listing states exactly what is servable without loading anything, and pooling
several intervals side by side needs no new convention.

**Nothing is skipped silently.** A file this module cannot parse or cannot serve is recorded with the
reason and surfaced on the refusal path, because an operator who wrote `btcusdt-1h.joblib` should be told
about the hyphen rather than shown an empty inventory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import logging
from pathlib import Path
import re
from threading import RLock
from typing import Any

import joblib

from crypto_signal.labeling import BARRIER_FEATURE_COLUMNS
from crypto_signal_engine.application.errors import ModelUnavailable


#: The symbol part of a filename that answers for any symbol. Not a legal Binance symbol, so it can
#: never collide with a real override.
WILDCARD_SYMBOL = "_pooled"

SUFFIX = ".joblib"

#: Binance symbols are uppercase alphanumerics; nothing in the venue's universe carries an underscore,
#: which is what makes `rsplit("_", 1)` an unambiguous parse.
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{2,}$")

#: `1m` is a minute and `1M` is a month, so interval matching is case-sensitive on purpose. Uppercasing
#: an interval the way symbols are uppercased would quietly turn a minute model into a month one.
_INTERVAL_PATTERN = re.compile(r"^[1-9][0-9]*[mhdwM]$")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """What a servable artifact declares about itself.

    `atr_window` and `max_horizon` are here because serving has to reproduce the training assumption
    exactly. Barrier distances arrive from the caller as percentages and are divided by ATR to reach the
    units the model was trained in; computing that ATR over a different window than the labeller used
    silently rescales every barrier input, and the model answers a question nobody asked. Same for the
    horizon: it is the label's definition of "did not resolve", not a serving preference.
    """

    model_id: str
    model_version: str
    project_version: str
    symbols: tuple[str, ...]
    interval: str
    trained_at: datetime
    feature_columns: tuple[str, ...]
    atr_window: int
    max_horizon: int
    is_pooled: bool
    confidence_ceiling: float | None = None
    confidence_attainment: tuple[tuple[float, float], ...] = ()

    #: How raw scores became probabilities, as the training run recorded it. Empty when the bundle
    #: predates the field. Reported over the wire because a caller thresholding on `confidence` is
    #: entitled to know whether anything calibrated it — an uncalibrated GBM score is not a probability,
    #: and "none, class-weighted estimator" is a real and defensible answer that should be visible
    #: rather than inferred from silence.
    calibration_method: str = ""

    @property
    def feature_count(self) -> int:
        return len(self.feature_columns)

    def covers(self, symbol: str) -> bool:
        return self.is_pooled or symbol.upper() in self.symbols

    def is_reachable(self, threshold: float, minimum_share: float = 0.001) -> bool:
        """Whether a confidence floor leaves enough of this model's distribution above it to ever fire.

        Unmeasured reach answers `True`: refusing a threshold on the grounds that nobody checked would
        make an unmeasured model unusable, which is a worse failure than an unenforced check.
        """
        if not self.confidence_attainment:
            return True
        below = [pair for pair in self.confidence_attainment if pair[0] <= threshold]
        share = below[-1][1] if below else 1.0
        return share >= minimum_share


@dataclass(slots=True)
class LoadedModel:
    """A loaded estimator, its descriptor, and the lock that serialises access to it.

    One lock per model rather than one for the registry. The original single-artifact loader serialised
    inference to avoid depending on any estimator's thread-safety, which is worth keeping; extending that
    one lock across every model in the registry would serialise unrelated symbols against each other and
    buy nothing, since the estimators are separate objects.
    """

    descriptor: ModelDescriptor
    estimator: Any
    fingerprint: tuple[int, int]
    _lock: RLock = field(default_factory=RLock, repr=False)

    def predict_proba(self, features: Any) -> Any:
        with self._lock:
            return self.estimator.predict_proba(features)

    @property
    def classes_(self) -> Any:
        """The fitted class labels, so this object can be passed wherever an estimator is expected.

        `modeling.estimator.aligned_probabilities` — and therefore `choose_direction` above it — reads
        `predict_proba` and `classes_` off the same object. Exposing `classes_` here lets the serving
        layer hand it a `LoadedModel` instead of reaching past to `.estimator`, which would take
        inference outside the lock this class exists to hold. Reading the attribute is not inference and
        does not need serialising: it is set once at fit time and never mutated.
        """
        return self.estimator.classes_


@dataclass(frozen=True, slots=True)
class Candidate:
    """An artifact the registry might load, before anything is opened.

    A file in the model directory states its identity in its name, which is what lets the whole
    directory be inventoried without reading a single artifact. The standalone `ML_MODEL_PATH` file does
    not — it is whatever it is, under whatever name it was deployed with — so its symbol and interval
    stay empty here and come from its metadata once loaded. That is safe for exactly one file, and would
    not be for a directory: deriving identity from metadata at scale means opening every artifact to
    find out whether any of them answers the question.
    """

    path: Path
    symbol: str = ""
    interval: str = ""

    @property
    def names_its_identity(self) -> bool:
        return bool(self.interval)

    @property
    def is_pooled(self) -> bool:
        return self.symbol == WILDCARD_SYMBOL

    @property
    def key(self) -> tuple[str, str]:
        return (self.symbol, self.interval)


def parse_artifact_name(path: Path) -> Candidate | None:
    """`BTCUSDT_1h.joblib` or `_pooled_1h.joblib` to a candidate; `None` if the name is not one of those."""
    if path.suffix != SUFFIX:
        return None
    stem = path.stem
    symbol, separator, interval = stem.rpartition("_")
    if not separator or not _INTERVAL_PATTERN.match(interval):
        return None
    if symbol != WILDCARD_SYMBOL and not _SYMBOL_PATTERN.match(symbol):
        return None
    return Candidate(path=path, symbol=symbol, interval=interval)


class ModelRegistry:
    """Scans a directory of artifacts and answers `(symbol, interval)` requests from it.

    Loading is lazy: a directory of thirty models costs nothing until something asks for one, which
    matters because the registry is constructed during server start-up and the container mount is read
    at that moment. Each entry is cached against the file's modification time and size, so replacing an
    artifact on a mounted volume is picked up on the next request without a restart, and a file that has
    not changed is never re-read or re-hashed.
    """

    def __init__(self, directory: Path, single_artifact: Path | None = None) -> None:
        self._directory = directory
        self._single_artifact = single_artifact
        self._lock = RLock()
        self._loaded: dict[tuple[str, str], LoadedModel] = {}
        self._rejected: dict[str, str] = {}

    # -- inventory ------------------------------------------------------------------------------

    def scan(self) -> tuple[Candidate, ...]:
        """Filenames that could serve, cheapest possible pass: no artifact is opened.

        Files that look like artifacts but cannot be parsed are recorded rather than dropped, so the
        refusal path can explain a typo instead of reporting an empty directory.
        """
        candidates: dict[tuple[str, str], Candidate] = {}
        paths = sorted(self._directory.glob(f"*{SUFFIX}")) if self._directory.is_dir() else []
        present = {path.name for path in paths}
        unparseable: dict[str, str] = {}

        for path in paths:
            candidate = parse_artifact_name(path)
            if candidate is None:
                unparseable[path.name] = (
                    f"expected <SYMBOL>_<INTERVAL>{SUFFIX} or {WILDCARD_SYMBOL}_<INTERVAL>{SUFFIX}"
                )
                continue
            candidates[candidate.key] = candidate

        with self._lock:
            # Merge rather than replace. A verdict reached by *loading* a file — the legacy artifact that
            # carries no barrier inputs, the override whose bundle names another pair — is the most useful
            # thing the registry knows, and rebuilding this dict from filenames alone would discard it on
            # every request, leaving the inventory advertising artifacts that cannot serve. Only entries
            # whose file has gone are dropped; a successful load clears its own entry in `_entry`.
            standalone = self._single_artifact.name if self._single_artifact else None
            self._rejected = {
                name: reason
                for name, reason in self._rejected.items()
                if name in present or name == standalone
            } | unparseable
        return tuple(candidates.values())

    def _standalone(self) -> LoadedModel | None:
        """The `ML_MODEL_PATH` artifact, or `None` if it is unset, absent, or cannot serve.

        Deliberately swallows its own load failure into `rejections()` instead of raising. It is the
        fallback: when a directory model already answered, a broken standalone file is irrelevant, and
        when nothing answered the operator needs to see it in the inventory alongside everything else
        rather than as the sole error.
        """
        if self._single_artifact is None or not self._single_artifact.is_file():
            return None
        try:
            return self._entry(Candidate(path=self._single_artifact))
        except ModelUnavailable as exc:
            self._reject(self._single_artifact.name, str(exc))
            return None

    @property
    def directory(self) -> Path:
        """Where artifacts are looked for. Read-only, and named in every "nothing servable" message."""
        return self._directory

    def available(self) -> tuple[ModelDescriptor, ...]:
        """Descriptors for everything servable — loads each artifact once.

        This is what `GetCapabilities` answers from, so it reports what the engine can *actually* do:
        an artifact that fails validation is excluded here and named in `rejections()`, rather than
        being advertised and then failing at the first request for it.
        """
        descriptors: list[ModelDescriptor] = []
        standalone = self._standalone()
        if standalone is not None:
            descriptors.append(standalone.descriptor)
        for candidate in self.scan():
            try:
                descriptors.append(self._entry(candidate).descriptor)
            except ModelUnavailable as exc:
                self._reject(candidate.path.name, str(exc))
        return tuple(descriptors)

    def rejections(self) -> dict[str, str]:
        """Files that look like artifacts but cannot serve, and why."""
        with self._lock:
            return dict(self._rejected)

    def _reject(self, name: str, reason: str) -> None:
        """Record why a file cannot serve, warning once per distinct reason.

        Once, because resolution runs on every request: a permanently broken artifact in the mount would
        otherwise emit a warning per signal and bury everything else in the log.
        """
        with self._lock:
            already_known = self._rejected.get(name) == reason
            self._rejected[name] = reason
        if not already_known:
            logger.warning("Artifact cannot serve | file=%s | reason=%s", name, reason)

    # -- resolution -----------------------------------------------------------------------------

    def resolve(self, symbol: str, interval: str) -> LoadedModel:
        """The model that may answer for `(symbol, interval)`: exact match, else pooled, else refuse.

        Each step is best-effort, and the reason is worth stating because it looks like leniency. A
        per-symbol override is an *optimisation* over the pooled model, not a precondition for serving
        the symbol — so an override that fails to load, or whose bundle turns out to have been trained on
        some other pair, must not deny a request the pooled model can answer. It is recorded in
        `rejections()` and logged, and resolution continues.

        This is not the venue-substitution antipattern it superficially resembles. Every response names
        the `model_id` and `model_version` that produced it, so a caller receiving the pooled answer can
        see that it did; what would be unacceptable is answering from a *different interval*, and that
        cannot happen because the interval is part of every lookup key.
        """
        wanted = symbol.strip().upper()
        candidates = self.scan()
        by_key = {candidate.key: candidate for candidate in candidates}

        for key in ((wanted, interval), (WILDCARD_SYMBOL, interval)):
            candidate = by_key.get(key)
            if candidate is None:
                continue
            try:
                model = self._entry(candidate)
            except ModelUnavailable as exc:
                self._reject(candidate.path.name, str(exc))
                continue
            if model.descriptor.covers(wanted):
                return model
            # A file whose bundle disagrees with its name. Serving it under the requested symbol would
            # attribute another pair's model to this one, so it is refused as an override — but the
            # pooled model behind it is still allowed to answer.
            self._reject(
                candidate.path.name,
                f"named for {candidate.symbol} but trained on {', '.join(model.descriptor.symbols)}",
            )

        standalone = self._standalone()
        if (
            standalone is not None
            and standalone.descriptor.interval == interval
            and standalone.descriptor.covers(wanted)
        ):
            return standalone

        raise ModelUnavailable(self._unavailable_message(wanted, interval, candidates))

    def _unavailable_message(
        self,
        symbol: str,
        interval: str,
        candidates: tuple[Candidate, ...],
    ) -> str:
        rejected = self.rejections()
        # Only advertise what could actually answer. A candidate already known to be unservable belongs in
        # the skipped list with its reason, not in a list an operator will read as "these five work".
        servable = [candidate for candidate in candidates if candidate.path.name not in rejected]
        if not servable:
            detail = f"no usable artifacts found in {self._directory}"
        else:
            served = ", ".join(
                f"{'any symbol' if candidate.is_pooled else candidate.symbol} {candidate.interval}"
                for candidate in servable
            )
            detail = f"available: {served}"
        if rejected:
            skipped = "; ".join(f"{name} ({reason})" for name, reason in sorted(rejected.items()))
            detail = f"{detail}. Skipped: {skipped}"
        return f"No model can serve {symbol} {interval} — {detail}"

    # -- loading --------------------------------------------------------------------------------

    def _entry(self, candidate: Candidate) -> LoadedModel:
        fingerprint = _fingerprint(candidate.path)
        with self._lock:
            cached = self._loaded.get(candidate.key)
            if cached is not None and cached.fingerprint == fingerprint:
                return cached

        # Deliberately outside the registry lock: loading is slow, and holding the map lock through it
        # would block every other symbol's requests behind one cold artifact. Two threads racing the
        # same cold entry both load it and the second overwrites the first, which costs one redundant
        # read and is otherwise harmless.
        model = _load(candidate, fingerprint)
        with self._lock:
            self._loaded[candidate.key] = model
            self._rejected.pop(candidate.path.name, None)
        logger.info(
            "Loaded model | file=%s | id=%s | version=%s | symbols=%s | features=%s",
            candidate.path.name,
            model.descriptor.model_id,
            model.descriptor.model_version[:12],
            len(model.descriptor.symbols) if not model.descriptor.is_pooled else "pooled",
            model.descriptor.feature_count,
        )
        return model


def _fingerprint(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise ModelUnavailable("the file is unreadable") from exc
    return (stat.st_mtime_ns, stat.st_size)


def _load(candidate: Candidate, fingerprint: tuple[int, int]) -> LoadedModel:
    # Deliberately broad. Reading a file whose shape is not guaranteed fails in as many ways as there are
    # pickle opcodes: a truncated bundle surfaces as `IndexError` from inside the unpickler, one written
    # against another library version as `AttributeError` or `ModuleNotFoundError`, a directory entry that
    # is not a bundle at all as almost anything. Enumerating the types means the first unenumerated one
    # escapes as a 500 — and the whole point of the registry is that one bad file on the mount cannot deny
    # a request every other file could serve. Every caller of this function records the reason and moves on.
    try:
        payload = candidate.path.read_bytes()
        bundle = joblib.load(candidate.path)
        estimator = bundle["model"]
        feature_columns = tuple(str(column) for column in bundle["feature_columns"])
        metadata = bundle["metadata"]
        interval = str(metadata["interval"])
        symbols = _symbols(metadata)
        trained_at = datetime.fromisoformat(str(metadata["trained_at_utc"]))
        atr_window = int(metadata["atr_window"])
        max_horizon = int(metadata["max_horizon"])
        project_version = str(metadata.get("project_version", "unknown"))
    except Exception as exc:
        raise ModelUnavailable(f"not a valid model bundle: {type(exc).__name__}: {exc}") from exc

    if not hasattr(estimator, "predict_proba"):
        raise ModelUnavailable("the estimator cannot produce probabilities")

    # The check that keeps a legacy close-to-close artifact from being served as a barrier model. Without
    # it the mismatch surfaces as a feature-count error inside `predict_proba` on the first real request,
    # by which time the caller sees an internal error instead of "this artifact answers a different
    # question".
    missing = [column for column in BARRIER_FEATURE_COLUMNS if column not in feature_columns]
    if missing:
        raise ModelUnavailable(
            f"not trained on barrier inputs (missing {', '.join(missing)}), so it cannot answer a "
            "take-profit/stop-loss request"
        )

    if candidate.names_its_identity:
        if interval != candidate.interval:
            raise ModelUnavailable(
                f"named for {candidate.interval} candles but trained on {interval}; every feature is "
                "measured in candle counts, so the two are not interchangeable"
            )
        # The filename declares intent that the bundle cannot: `_pooled_1h` offers to answer for symbols
        # it never saw, while `BTCUSDT_1h` is an override and stays scoped to its own pair even if it was
        # trained on a pooled set.
        is_pooled = candidate.is_pooled
        model_id = f"{candidate.symbol}:{interval}"
    else:
        # No declared intent for the standalone artifact, so it is read from the training set: a bundle
        # covering several pairs generalises across them by construction, and one covering a single pair
        # has no claim beyond it.
        is_pooled = len(symbols) > 1
        model_id = f"{WILDCARD_SYMBOL if is_pooled else symbols[0]}:{interval}"

    ceiling, attainment = _reach(metadata)
    descriptor = ModelDescriptor(
        model_id=model_id,
        # SHA-256 of the artifact bytes: two engines serving the same file report the same version, and
        # a rebuild that changes nothing does not look like a new model.
        model_version=hashlib.sha256(payload).hexdigest(),
        project_version=project_version,
        symbols=symbols,
        interval=interval,
        trained_at=trained_at,
        feature_columns=feature_columns,
        atr_window=atr_window,
        max_horizon=max_horizon,
        is_pooled=is_pooled,
        confidence_ceiling=ceiling,
        confidence_attainment=attainment,
        calibration_method=str((metadata.get("calibration") or {}).get("method") or ""),
    )
    return LoadedModel(descriptor=descriptor, estimator=estimator, fingerprint=fingerprint)


def _symbols(metadata: dict[str, Any]) -> tuple[str, ...]:
    """The pairs the bundle says it was trained on, from either the pooled or the single-symbol key."""
    raw = metadata.get("symbols")
    if raw is None:
        raw = [metadata["symbol"]]
    symbols = tuple(str(symbol).strip().upper() for symbol in raw if str(symbol).strip())
    if not symbols:
        raise ValueError("the bundle names no training symbols")
    return symbols


def _reach(metadata: dict[str, Any]) -> tuple[float | None, tuple[tuple[float, float], ...]]:
    """The measured confidence ceiling, if the training run recorded one.

    Optional because a model can be trained without the calibration assessment, but worth carrying
    whenever it exists: it is the only thing that lets a caller be told its confidence floor is
    unreachable, rather than discovering it through an indefinite absence of signals.
    """
    reach = (metadata.get("calibration") or {}).get("reach")
    if not reach:
        return None, ()
    ceiling = reach.get("ceiling")
    attainment = tuple(
        sorted((float(level), float(share)) for level, share in (reach.get("attainment") or {}).items())
    )
    return (float(ceiling) if ceiling is not None else None), attainment
