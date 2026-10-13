"""Dynamic Replanning public API."""

from __future__ import annotations

from app.schemas.replanning import (
    AffectedElement,
    ConfirmationResult,
    ConsistencyCheck,
    Decision,
    IntentAnchor,
    NextAction,
    RevisedActivity,
    RevisedPlan,
    Severity,
    TurnRecord,
    Vibe,
)
from app.replanning.dynamic_replanning.state_manager import (
    ReplanningStateManager,
)
from app.replanning.dynamic_replanning.intent_preserver import (
    IntentPreserver,
)
from app.replanning.dynamic_replanning.alternative_finder import (
    AlternativeFinder,
)
from app.replanning.dynamic_replanning.multi_turn_tracker import (
    MultiTurnTracker,
)
from app.replanning.dynamic_replanning.cross_turn_consistency import (
    CrossTurnConsistency,
)
from app.replanning.dynamic_replanning.confirmation_flow import (
    ConfirmationFlow,
)
from app.replanning.dynamic_replanning.utils import (
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_PATH,
    call_component1_api,
    call_component2_api,
    deep_merge,
    format_revised_plan,
    generate_id,
    get_env_api_key,
    load_config,
    now_utc,
    setup_logging,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DEFAULT_CONFIG",
    "DEFAULT_CONFIG_PATH",
    "load_config",
    "deep_merge",
    "generate_id",
    "now_utc",
    "format_revised_plan",
    "get_env_api_key",
    "setup_logging",
    "call_component1_api",
    "call_component2_api",
    "Vibe",
    "Severity",
    "Decision",
    "NextAction",
    "IntentAnchor",
    "AffectedElement",
    "RevisedActivity",
    "RevisedPlan",
    "TurnRecord",
    "ConsistencyCheck",
    "ConfirmationResult",
    # State
    "ReplanningStateManager",
    # Intent
    "IntentPreserver",
    # Alternatives
    "AlternativeFinder",
    # Multi-turn
    "MultiTurnTracker",
    "CrossTurnConsistency",
    # Confirmation
    "ConfirmationFlow",
]