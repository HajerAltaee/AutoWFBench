"""Fixed optimization principles, defined independently of benchmark scorecards."""

PRINCIPLES = {
    "correctness": (
        "Satisfy the public task, preserve required behavior, validate important "
        "outputs, and reject optimizations that break functionality."
    ),
    "reliability": (
        "Reduce fragile dependencies and unnecessary failure points; handle "
        "predictable failures with bounded, verifiable recovery."
    ),
    "efficiency": (
        "Avoid redundant work, unnecessary model or tool calls, repeated "
        "computation, and avoidable sequential execution."
    ),
    "simplicity": (
        "Prefer direct, understandable execution paths and remove orchestration "
        "or branching that provides no functional value."
    ),
}

MUTATION_STRATEGIES = tuple(PRINCIPLES)
