from __future__ import annotations


def blended_city_rate_per_minute(
    city_event_count: int,
    observation_minutes: float,
    global_rate_per_minute: float,
    min_city_events: int = 20,
) -> tuple[float, str]:
    if observation_minutes <= 0:
        return global_rate_per_minute, "global"

    if city_event_count <= 0:
        return global_rate_per_minute, "global"

    city_rate = city_event_count / observation_minutes
    weight = city_event_count / float(city_event_count + max(min_city_events, 1))
    blended = (weight * city_rate) + ((1.0 - weight) * global_rate_per_minute)
    if city_event_count < min_city_events:
        return blended, "blended_global"
    return blended, "city"


def smoothed_multiplier(
    bucket_count: int,
    total_count: int,
    num_buckets: int,
    pseudo_count: float,
) -> float:
    if num_buckets <= 0:
        return 1.0
    if total_count <= 0:
        return 1.0
    pseudo = max(pseudo_count, 0.0)
    probability = (bucket_count + pseudo) / (total_count + (num_buckets * pseudo))
    return probability * num_buckets

