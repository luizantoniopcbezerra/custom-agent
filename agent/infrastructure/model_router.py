# Maps difficulty score ranges to free OpenRouter models.
# Lower scores (trivial) use faster models; higher scores use stronger reasoning models.
_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"


def route_model(score: int) -> str:  # noqa: ARG001
    return _MODEL
