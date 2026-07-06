"""Catalyst quality classification for pre-market short-candidate research."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "catalyst.json"


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1"}:
            return True
        if normalized in {"false", "f", "no", "n", "0"}:
            return False
    return None


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(pattern in normalized for pattern in patterns)


def _text_items(record: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "catalyst_text",
        "catalyst_summary",
        "headline",
        "headlines",
        "news",
        "recent_news",
        "news_headlines",
        "recent_filings",
        "sec_filings",
        "filings",
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
                    for field_name in (
                        "headline",
                        "title",
                        "summary",
                        "description",
                        "form",
                        "form_type",
                        "type",
                    )
                ]
                text = " ".join(piece for piece in pieces if piece).strip()
                if text:
                    texts.append(text)
            else:
                texts.append(str(item))
    return [text for text in texts if text.strip()]


@dataclass(frozen=True)
class CatalystRules:
    weak_score_threshold: int = 3
    medium_score_threshold: int = 2
    strong_score_threshold: int = 3
    earnings_guidance_points: int = 4
    acquisition_buyout_points: int = 5
    fda_approval_points: int = 4
    material_contract_points: int = 3
    debt_refinancing_points: int = 3
    profitability_inflection_points: int = 3
    analyst_upgrade_points: int = 2
    product_launch_points: int = 2
    detailed_partnership_points: int = 2
    sector_sympathy_points: int = 1
    vague_ai_points: int = 2
    crypto_blockchain_points: int = 2
    non_binding_loi_points: int = 3
    unnamed_partner_points: int = 2
    no_financial_terms_points: int = 2
    strategic_alternatives_points: int = 2
    social_media_meme_points: int = 3
    old_news_points: int = 2
    short_squeeze_points: int = 3


@dataclass(frozen=True)
class CatalystMetrics:
    symbol: str
    text_count: int
    strong_score: int
    medium_score: int
    weak_catalyst_score: int
    assessed_signal_count: int


@dataclass(frozen=True)
class CatalystAssessment:
    symbol: str
    category: str
    weak_catalyst_score: int
    strong_catalyst_score: int
    medium_catalyst_score: int
    metrics: CatalystMetrics
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_catalyst_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> CatalystRules:
    """Load catalyst-classification rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    points = raw.get("points", {})
    return CatalystRules(
        weak_score_threshold=int(thresholds.get("weak_score", 3)),
        medium_score_threshold=int(thresholds.get("medium_score", 2)),
        strong_score_threshold=int(thresholds.get("strong_score", 3)),
        earnings_guidance_points=int(points.get("earnings_guidance", 4)),
        acquisition_buyout_points=int(points.get("acquisition_buyout", 5)),
        fda_approval_points=int(points.get("fda_approval", 4)),
        material_contract_points=int(points.get("material_contract", 3)),
        debt_refinancing_points=int(points.get("debt_refinancing", 3)),
        profitability_inflection_points=int(
            points.get("profitability_inflection", 3)
        ),
        analyst_upgrade_points=int(points.get("analyst_upgrade", 2)),
        product_launch_points=int(points.get("product_launch", 2)),
        detailed_partnership_points=int(points.get("detailed_partnership", 2)),
        sector_sympathy_points=int(points.get("sector_sympathy", 1)),
        vague_ai_points=int(points.get("vague_ai", 2)),
        crypto_blockchain_points=int(points.get("crypto_blockchain", 2)),
        non_binding_loi_points=int(points.get("non_binding_loi", 3)),
        unnamed_partner_points=int(points.get("unnamed_partner", 2)),
        no_financial_terms_points=int(points.get("no_financial_terms", 2)),
        strategic_alternatives_points=int(points.get("strategic_alternatives", 2)),
        social_media_meme_points=int(points.get("social_media_meme", 3)),
        old_news_points=int(points.get("old_news", 2)),
        short_squeeze_points=int(points.get("short_squeeze", 3)),
    )


def evaluate_catalyst(
    record: Mapping[str, Any], rules: CatalystRules | None = None
) -> CatalystAssessment:
    """Classify catalyst quality without filtering the record out."""

    active_rules = rules or CatalystRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    explicit_category = str(
        _first_present(record, "catalyst_category", "catalyst_quality") or ""
    ).strip().lower()
    no_obvious_catalyst = _as_bool(
        _first_present(record, "no_obvious_catalyst", "no_catalyst")
    )

    texts = _text_items(record)
    combined_text = " ".join(texts)
    strong_score = 0
    medium_score = 0
    weak_score = 0
    reasons: list[str] = []
    warnings: list[str] = []
    assessed_signal_count = 0

    if not symbol:
        warnings.append("missing_symbol")

    def add_signal(kind: str, reason: str, points: int) -> None:
        nonlocal strong_score, medium_score, weak_score, assessed_signal_count
        assessed_signal_count += 1
        reasons.append(reason)
        if kind == "strong":
            strong_score += points
        elif kind == "medium":
            medium_score += points
        else:
            weak_score += points

    if explicit_category in {"strong", "medium", "weak", "none"}:
        assessed_signal_count += 1
        reasons.append(f"explicit_{explicit_category}_catalyst")
        if explicit_category == "strong":
            strong_score += active_rules.strong_score_threshold
        elif explicit_category == "medium":
            medium_score += active_rules.medium_score_threshold
        elif explicit_category == "weak":
            weak_score += active_rules.weak_score_threshold

    if no_obvious_catalyst is True:
        assessed_signal_count += 1
        reasons.append("no_obvious_catalyst")

    if combined_text:
        if _contains_any(
            combined_text,
            (
                "earnings beat",
                "beats earnings",
                "guidance raise",
                "raises guidance",
                "raised guidance",
                "lifts outlook",
                "increases outlook",
            ),
        ):
            add_signal("strong", "earnings_guidance", active_rules.earnings_guidance_points)

        if _contains_any(
            combined_text,
            (
                "acquisition",
                "buyout",
                "takeover",
                "to be acquired",
                "merger agreement",
                "definitive agreement to acquire",
            ),
        ):
            add_signal("strong", "acquisition_buyout", active_rules.acquisition_buyout_points)

        if _contains_any(
            combined_text,
            (
                "fda approval",
                "fda approves",
                "approved by the fda",
                "phase 3 met",
                "met primary endpoint",
                "positive phase 3",
            ),
        ):
            add_signal("strong", "fda_approval", active_rules.fda_approval_points)

        if _contains_any(combined_text, ("contract", "purchase order", "award")) and (
            "$" in combined_text
            or _contains_any(combined_text, ("million", "billion", "multi-year"))
        ):
            add_signal("strong", "material_contract", active_rules.material_contract_points)

        if _contains_any(
            combined_text,
            (
                "debt refinancing",
                "refinancing",
                "extends maturity",
                "credit facility",
            ),
        ):
            add_signal("strong", "debt_refinancing", active_rules.debt_refinancing_points)

        if _contains_any(
            combined_text,
            (
                "turns profitable",
                "achieves profitability",
                "profitability inflection",
                "positive cash flow",
            ),
        ):
            add_signal(
                "strong",
                "profitability_inflection",
                active_rules.profitability_inflection_points,
            )

        if _contains_any(
            combined_text,
            ("analyst upgrade", "upgraded by", "price target raised", "raises price target"),
        ):
            add_signal("medium", "analyst_upgrade", active_rules.analyst_upgrade_points)

        if _contains_any(
            combined_text,
            ("product launch", "launches product", "commercial launch", "new product"),
        ):
            add_signal("medium", "product_launch", active_rules.product_launch_points)

        if _contains_any(combined_text, ("partnership", "collaboration")):
            add_signal(
                "medium",
                "detailed_partnership",
                active_rules.detailed_partnership_points,
            )

        if _contains_any(
            combined_text,
            ("sector rally", "sector sympathy", "sympathy move", "industry rally"),
        ):
            add_signal("medium", "sector_sympathy", active_rules.sector_sympathy_points)

        if _contains_any(
            combined_text,
            ("artificial intelligence", " ai ", "ai-powered", " ai-", "generative ai"),
        ):
            add_signal("weak", "vague_ai", active_rules.vague_ai_points)

        if _contains_any(
            combined_text,
            ("crypto", "blockchain", "bitcoin", "digital asset", "web3"),
        ):
            add_signal("weak", "crypto_blockchain", active_rules.crypto_blockchain_points)

        if _contains_any(
            combined_text,
            (
                "non-binding",
                "non binding",
                "letter of intent",
                " loi",
                "memorandum of understanding",
                " mou",
            ),
        ):
            add_signal("weak", "non_binding_loi", active_rules.non_binding_loi_points)

        if _contains_any(
            combined_text,
            (
                "unnamed partner",
                "undisclosed customer",
                "confidential customer",
                "leading global company",
            ),
        ):
            add_signal("weak", "unnamed_partner", active_rules.unnamed_partner_points)

        if _contains_any(
            combined_text,
            (
                "no financial terms",
                "terms not disclosed",
                "financial terms were not disclosed",
                "no financial details",
            ),
        ):
            add_signal("weak", "no_financial_terms", active_rules.no_financial_terms_points)

        if _contains_any(
            combined_text,
            ("strategic alternatives", "review strategic alternatives", "strategic review"),
        ):
            add_signal(
                "weak",
                "strategic_alternatives",
                active_rules.strategic_alternatives_points,
            )

        if _contains_any(
            combined_text,
            ("social media", "reddit", "meme", "retail traders", "stocktwits", "viral"),
        ):
            add_signal("weak", "social_media_meme", active_rules.social_media_meme_points)

        if _contains_any(combined_text, ("old news", "resurfaced", "previously announced")):
            add_signal("weak", "old_news", active_rules.old_news_points)

        if _contains_any(combined_text, ("short squeeze", "squeeze")):
            add_signal("weak", "short_squeeze", active_rules.short_squeeze_points)
    else:
        warnings.append("missing_catalyst_text")

    if no_obvious_catalyst is True and strong_score == 0 and medium_score == 0 and weak_score == 0:
        category = "none"
    elif assessed_signal_count == 0:
        category = "unknown"
        warnings.append("catalyst_data_missing")
    elif (
        strong_score >= active_rules.strong_score_threshold
        and strong_score >= weak_score
        and strong_score >= medium_score
    ):
        category = "strong"
    elif weak_score >= active_rules.weak_score_threshold and weak_score >= medium_score:
        category = "weak"
    elif medium_score >= active_rules.medium_score_threshold:
        category = "medium"
    elif no_obvious_catalyst is True:
        category = "none"
    else:
        category = "unknown"

    metrics = CatalystMetrics(
        symbol=symbol,
        text_count=len(texts),
        strong_score=strong_score,
        medium_score=medium_score,
        weak_catalyst_score=weak_score,
        assessed_signal_count=assessed_signal_count,
    )

    return CatalystAssessment(
        symbol=symbol,
        category=category,
        weak_catalyst_score=weak_score,
        strong_catalyst_score=strong_score,
        medium_catalyst_score=medium_score,
        metrics=metrics,
        reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def evaluate_catalyst_batch(
    records: Iterable[Mapping[str, Any]], rules: CatalystRules | None = None
) -> list[CatalystAssessment]:
    """Classify catalyst quality for a batch of normalized records."""

    active_rules = rules or CatalystRules()
    return [evaluate_catalyst(record, active_rules) for record in records]
