"""Hype and crowd-attention scoring for pre-market short-candidate research."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "hype.json"


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = f" {text.lower()} "
    return any(pattern in normalized for pattern in patterns)


def _text_items(record: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "headline",
        "headlines",
        "news",
        "recent_news",
        "news_headlines",
        "social_posts",
        "social_text",
        "social_mentions_text",
        "catalyst_text",
        "catalyst_summary",
    ):
        value = record.get(key)
        if value is not None and value != "":
            values.append(value)

    texts: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, Mapping):
                pieces = [
                    str(item.get(field_name, ""))
                    for field_name in ("headline", "title", "summary", "text", "body")
                ]
                text = " ".join(piece for piece in pieces if piece).strip()
                if text:
                    texts.append(text)
            else:
                texts.append(str(item))
    return [text for text in texts if text.strip()]


def _pct_change(new_value: float, old_value: float) -> float:
    return ((new_value - old_value) / old_value) * 100.0


@dataclass(frozen=True)
class HypeRules:
    moderate_score: int = 4
    high_score: int = 8
    abnormal_social_mentions_ratio: float = 3.0
    abnormal_headline_count_ratio: float = 3.0
    high_headline_count: int = 3
    low_float_shares: float = 20_000_000.0
    strong_premarket_move_pct: float = 20.0
    meme_keywords_points: int = 3
    social_attention_points: int = 3
    short_squeeze_language_points: int = 3
    buzzword_theme_points: int = 2
    abnormal_headline_velocity_points: int = 2
    multiple_same_day_headlines_points: int = 1
    retail_trader_language_points: int = 2
    low_float_hype_points: int = 2
    attention_driven_move_points: int = 2


@dataclass(frozen=True)
class HypeMetrics:
    symbol: str
    text_count: int
    social_mentions: float | None
    average_social_mentions: float | None
    social_mentions_ratio: float | None
    headline_count: float | None
    average_headline_count: float | None
    headline_count_ratio: float | None
    float_shares: float | None
    premarket_move_pct: float | None
    assessed_signal_count: int


@dataclass(frozen=True)
class HypeAssessment:
    symbol: str
    hype_score: int
    hype_level: str
    metrics: HypeMetrics
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_hype_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> HypeRules:
    """Load hype scoring rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    points = raw.get("points", {})
    return HypeRules(
        moderate_score=int(thresholds.get("moderate_score", 4)),
        high_score=int(thresholds.get("high_score", 8)),
        abnormal_social_mentions_ratio=float(
            thresholds.get("abnormal_social_mentions_ratio", 3.0)
        ),
        abnormal_headline_count_ratio=float(
            thresholds.get("abnormal_headline_count_ratio", 3.0)
        ),
        high_headline_count=int(thresholds.get("high_headline_count", 3)),
        low_float_shares=float(thresholds.get("low_float_shares", 20_000_000)),
        strong_premarket_move_pct=float(
            thresholds.get("strong_premarket_move_pct", 20.0)
        ),
        meme_keywords_points=int(points.get("meme_keywords", 3)),
        social_attention_points=int(points.get("social_attention", 3)),
        short_squeeze_language_points=int(points.get("short_squeeze_language", 3)),
        buzzword_theme_points=int(points.get("buzzword_theme", 2)),
        abnormal_headline_velocity_points=int(
            points.get("abnormal_headline_velocity", 2)
        ),
        multiple_same_day_headlines_points=int(
            points.get("multiple_same_day_headlines", 1)
        ),
        retail_trader_language_points=int(points.get("retail_trader_language", 2)),
        low_float_hype_points=int(points.get("low_float_hype", 2)),
        attention_driven_move_points=int(points.get("attention_driven_move", 2)),
    )


def evaluate_hype(
    record: Mapping[str, Any], rules: HypeRules | None = None
) -> HypeAssessment:
    """Score crowd attention and hype amplification without filtering the record out."""

    active_rules = rules or HypeRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    texts = _text_items(record)
    combined_text = " ".join(texts)
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0
    assessed_signal_count = 0

    social_mentions = _as_float(
        _first_present(
            record,
            "social_mentions",
            "social_mentions_today",
            "stocktwits_mentions",
            "reddit_mentions",
        )
    )
    average_social_mentions = _as_float(
        _first_present(
            record,
            "average_social_mentions",
            "avg_social_mentions",
            "baseline_social_mentions",
        )
    )
    headline_count = _as_float(
        _first_present(
            record,
            "headline_count",
            "headline_count_today",
            "news_count",
            "news_count_today",
        )
    )
    average_headline_count = _as_float(
        _first_present(
            record,
            "average_headline_count",
            "avg_headline_count",
            "baseline_headline_count",
        )
    )
    float_shares = _as_float(
        _first_present(record, "float_shares", "shares_float", "public_float", "float")
    )
    premarket_move_pct = _as_float(
        _first_present(record, "premarket_move_pct", "premarket_change_pct")
    )
    premarket_price = _as_float(
        _first_present(record, "premarket_price", "premarket_last", "price")
    )
    previous_close = _as_float(
        _first_present(record, "previous_close", "prev_close", "prior_close")
    )

    if premarket_move_pct is None and premarket_price is not None and previous_close:
        premarket_move_pct = _pct_change(premarket_price, previous_close)

    if not symbol:
        warnings.append("missing_symbol")

    def add_reason(reason: str, points: int) -> None:
        nonlocal score, assessed_signal_count
        assessed_signal_count += 1
        score += points
        reasons.append(reason)

    text_hype_signal = False
    if combined_text:
        if _contains_any(
            combined_text,
            (
                " meme ",
                " reddit ",
                " wallstreetbets ",
                " stocktwits ",
                " viral ",
                " to the moon ",
                " diamond hands ",
                " apes ",
                " yolo ",
            ),
        ):
            text_hype_signal = True
            add_reason("meme_keywords", active_rules.meme_keywords_points)

        if _contains_any(
            combined_text,
            (
                " social media ",
                " trending ",
                " influencer ",
                " influencers ",
                " twitter ",
                " x.com ",
                " fintwit ",
            ),
        ):
            text_hype_signal = True
            add_reason("social_attention", active_rules.social_attention_points)

        if _contains_any(combined_text, (" short squeeze ", " squeeze ", " gamma squeeze ")):
            text_hype_signal = True
            add_reason(
                "short_squeeze_language",
                active_rules.short_squeeze_language_points,
            )

        if _contains_any(
            combined_text,
            (
                " artificial intelligence ",
                " ai ",
                " ai-powered ",
                " generative ai ",
                " crypto ",
                " blockchain ",
                " bitcoin ",
                " quantum ",
                " web3 ",
            ),
        ):
            text_hype_signal = True
            add_reason("buzzword_theme", active_rules.buzzword_theme_points)

        if _contains_any(
            combined_text,
            (
                " retail traders ",
                " retail investors ",
                " day traders ",
                " momentum traders ",
                " chatroom ",
                " message board ",
            ),
        ):
            text_hype_signal = True
            add_reason(
                "retail_trader_language",
                active_rules.retail_trader_language_points,
            )
    else:
        warnings.append("missing_hype_text")

    social_mentions_ratio = None
    if social_mentions is None:
        warnings.append("missing_social_mentions")
    elif average_social_mentions is None or average_social_mentions <= 0:
        warnings.append("missing_average_social_mentions")
    else:
        social_mentions_ratio = social_mentions / average_social_mentions
        assessed_signal_count += 1
        if social_mentions_ratio >= active_rules.abnormal_social_mentions_ratio:
            add_reason("abnormal_social_mentions", active_rules.social_attention_points)

    if headline_count is None and texts:
        headline_count = float(len(texts))

    headline_count_ratio = None
    if headline_count is None:
        warnings.append("missing_headline_count")
    else:
        assessed_signal_count += 1
        if headline_count >= active_rules.high_headline_count:
            add_reason(
                "multiple_same_day_headlines",
                active_rules.multiple_same_day_headlines_points,
            )

        if average_headline_count is None or average_headline_count <= 0:
            warnings.append("missing_average_headline_count")
        else:
            headline_count_ratio = headline_count / average_headline_count
            if headline_count_ratio >= active_rules.abnormal_headline_count_ratio:
                add_reason(
                    "abnormal_headline_velocity",
                    active_rules.abnormal_headline_velocity_points,
                )

    if float_shares is None:
        warnings.append("missing_float_shares")
    else:
        assessed_signal_count += 1
        if float_shares <= active_rules.low_float_shares and (
            text_hype_signal
            or (social_mentions_ratio is not None and social_mentions_ratio >= active_rules.abnormal_social_mentions_ratio)
            or (headline_count_ratio is not None and headline_count_ratio >= active_rules.abnormal_headline_count_ratio)
        ):
            add_reason("low_float_hype", active_rules.low_float_hype_points)

    if premarket_move_pct is None:
        warnings.append("missing_premarket_move_pct")
    else:
        assessed_signal_count += 1
        if premarket_move_pct >= active_rules.strong_premarket_move_pct and (
            text_hype_signal
            or (social_mentions_ratio is not None and social_mentions_ratio >= active_rules.abnormal_social_mentions_ratio)
            or (headline_count_ratio is not None and headline_count_ratio >= active_rules.abnormal_headline_count_ratio)
        ):
            add_reason("attention_driven_move", active_rules.attention_driven_move_points)

    if assessed_signal_count == 0:
        hype_level = "unknown"
        warnings.append("hype_data_missing")
    elif score >= active_rules.high_score:
        hype_level = "high"
    elif score >= active_rules.moderate_score:
        hype_level = "moderate"
    else:
        hype_level = "low"

    metrics = HypeMetrics(
        symbol=symbol,
        text_count=len(texts),
        social_mentions=social_mentions,
        average_social_mentions=average_social_mentions,
        social_mentions_ratio=social_mentions_ratio,
        headline_count=headline_count,
        average_headline_count=average_headline_count,
        headline_count_ratio=headline_count_ratio,
        float_shares=float_shares,
        premarket_move_pct=premarket_move_pct,
        assessed_signal_count=assessed_signal_count,
    )

    return HypeAssessment(
        symbol=symbol,
        hype_score=score,
        hype_level=hype_level,
        metrics=metrics,
        reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def evaluate_hype_batch(
    records: Iterable[Mapping[str, Any]], rules: HypeRules | None = None
) -> list[HypeAssessment]:
    """Score hype for a batch of normalized records."""

    active_rules = rules or HypeRules()
    return [evaluate_hype(record, active_rules) for record in records]
