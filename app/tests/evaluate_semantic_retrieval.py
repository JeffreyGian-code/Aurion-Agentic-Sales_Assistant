"""Opt-in retrieval evaluation using public Markdown and synthetic buyer phrases."""

from dotenv import load_dotenv

from app.repositories.chroma_vehicle_knowledge import ChromaVehicleKnowledge
from app.repositories.vehicle_knowledge import VehicleKnowledge
from app.services.recommendation_service import DEFAULT_MIN_SIMILARITY


# Each row has a synthetic preference, the supporting topic, and the old route's tag.
DEVELOPMENT = [
    ("convenient for driving to work through the city each day", "commuting", "commuting"),
    ("gali mein aasani se park ho jaye", "parking", "parking"),
    ("keep suitcases out of the passenger cabin", "luggage", "boot_space"),
    ("SUV jaisa cabin chahiye family outings ke liye", "suv_layout", "family_use"),
    ("premium sound system with deep bass", None, "audio"),
    ("gaadi mein ventilated seats chahiye", None, "ventilated_seats"),
    ("can tow a heavy horse trailer", None, "towing"),
]
HOLDOUT = [
    ("easy weekday city office commute", "commuting", "commuting"),
    ("fit in a cramped parking spot", "parking", "parking"),
    ("suitcase ke liye cabin se alag boot", "luggage", "boot_space"),
    ("grocery bags load karne ke liye rear hatch", "loading", "cargo_access"),
    ("adaptive cruise and lane centering", None, "driver_assistance"),
    ("sunroof ho aur seat garam ho sake", None, "comfort_features"),
    ("strong resale value after five years", None, "resale"),
]


def predicted_topic_hits(hits, minimum):
    top_variants = {}
    for hit in hits:
        if hit.similarity >= minimum:
            top_variants.setdefault(hit.entry.id, hit.entry.evidence.topic)
    return list(top_variants.values())[:3]


def score(cases, predictions):
    return sum((topic in topics if topic else not topics)
               for (_, topic, _), topics in zip(cases, predictions, strict=True))


def calibrate(cases, groups):
    scores = sorted({hit.similarity for hits in groups for hit in hits if 0 < hit.similarity < 1})
    bounds = [0, *scores, 1]
    cutoffs = [(a + b) / 2 for a, b in zip(bounds, bounds[1:])]

    def grade(minimum):
        predictions = [predicted_topic_hits(hits, minimum) for hits in groups]
        false_positives = sum(bool(topics) for (_, topic, _), topics in zip(cases, predictions) if not topic)
        return score(cases, predictions), -false_positives, minimum

    return max(cutoffs, key=grade)


def main():
    load_dotenv()
    markdown = VehicleKnowledge()
    knowledge = ChromaVehicleKnowledge(markdown.all_entries())
    development_hits = knowledge.semantic_matches([phrase for phrase, _, _ in DEVELOPMENT], None)
    holdout_hits = knowledge.semantic_matches([phrase for phrase, _, _ in HOLDOUT], None)
    tuned = calibrate(DEVELOPMENT, development_hits)
    print(f"Development cutoff {tuned:.4f}; application default {DEFAULT_MIN_SIMILARITY:.4f}")
    for name, cases, groups in (
        ("Development", DEVELOPMENT, development_hits), ("Holdout", HOLDOUT, holdout_hits),
    ):
        baseline = [[topic] if markdown.retrieve([topic]) else [] for _, _, topic in cases]
        tuned_predictions = [predicted_topic_hits(hits, tuned) for hits in groups]
        configured = [predicted_topic_hits(hits, DEFAULT_MIN_SIMILARITY) for hits in groups]
        print(f"{name}: tuned {score(cases, tuned_predictions)}/{len(cases)}, "
              f"default {score(cases, configured)}/{len(cases)}, tags {score(cases, baseline)}/{len(cases)}")
        for (phrase, expected, _), hits, topics in zip(cases, groups, tuned_predictions, strict=True):
            best = max((hit.similarity for hit in hits), default=0)
            print(f"  {phrase} | expected={expected or 'clarify'} | returned={topics} | best={best:.3f}")


if __name__ == "__main__":
    main()
