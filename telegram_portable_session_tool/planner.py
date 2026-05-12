from __future__ import annotations

import random
from datetime import datetime

from .models import MessageDraft, SessionPlan, Target, ToolConfig, VisitPlanItem
from .sync_sources import build_message_target_candidates, resolve_targets


STATE_VERSION = 1


def default_state() -> dict:
    return {
        "version": STATE_VERSION,
        "message_cursor": 0,
        "message_target_cursor": 0,
        "messages_sent_total": 0,
        "history": [],
    }


def next_message_drafts(config: ToolConfig, state: dict) -> list[MessageDraft]:
    templates = list(config.message_policy.templates)
    if not templates:
        return []
    count = max(0, min(config.message_policy.drafts_per_run, len(templates)))
    total_limit = max(0, int(config.message_policy.total_message_limit))
    if total_limit > 0:
        messages_sent_total = max(0, int(state.get("messages_sent_total", 0)))
        remaining = max(0, total_limit - messages_sent_total)
        count = min(count, remaining)
    cursor = int(state.get("message_cursor", 0))
    drafts: list[MessageDraft] = []
    for index in range(count):
        template_index = (cursor + index) % len(templates)
        drafts.append(MessageDraft(index=index + 1, text=templates[template_index]))
    return drafts


def next_message_target(config: ToolConfig, state: dict, *, candidates: list[Target]) -> Target | None:
    if not candidates:
        if not config.message_policy.target_username.strip():
            return None
        return Target(
            target_id="message_policy_target",
            label=config.message_policy.target_username.strip(),
            handle=config.message_policy.target_username.strip(),
            kind="contact",
            source="message_policy",
            allowed_actions=("send_message",),
            consent_confirmed=True,
        )
    if config.message_policy.target_mode == "fixed":
        return candidates[0]
    cursor = int(state.get("message_target_cursor", 0))
    return candidates[cursor % len(candidates)]


def _random_view_seconds(config: ToolConfig, rng: random.Random) -> int:
    lower = min(config.session.view_min_seconds, config.session.view_max_seconds)
    upper = max(config.session.view_min_seconds, config.session.view_max_seconds)
    return rng.randint(lower, upper)


def _build_explicit_target_visits(config: ToolConfig, rng: random.Random) -> list[VisitPlanItem]:
    resolved_targets = resolve_targets(config)
    groups = list(resolved_targets.groups)
    contacts = list(resolved_targets.contacts)
    rng.shuffle(groups)
    rng.shuffle(contacts)
    groups = groups[: config.session.max_group_views_per_run]
    contacts = contacts[: config.session.max_contact_views_per_run]

    visits: list[VisitPlanItem] = []
    for target in [*groups, *contacts]:
        visits.append(
            VisitPlanItem(
                target_id=target.target_id,
                label=target.label,
                kind=target.kind,
                view_seconds=_random_view_seconds(config, rng),
                action="open_uri",
                uri=target.uri(),
            )
        )
    rng.shuffle(visits)
    return visits


def _build_current_profile_sidebar_visits(config: ToolConfig, rng: random.Random) -> list[VisitPlanItem]:
    visits: list[VisitPlanItem] = []
    y_min = min(config.session.sidebar_y_min_ratio, config.session.sidebar_y_max_ratio)
    y_max = max(config.session.sidebar_y_min_ratio, config.session.sidebar_y_max_ratio)
    for index in range(max(0, config.session.random_walk_visits_per_run)):
        visits.append(
            VisitPlanItem(
                target_id=f"current_profile_chat_{index + 1}",
                label=f"Current profile sidebar step {index + 1}",
                kind="existing_chat",
                view_seconds=_random_view_seconds(config, rng),
                action="sidebar_click",
                x_ratio=float(config.session.sidebar_x_ratio),
                y_ratio=rng.uniform(y_min, y_max),
            )
        )
    return visits


def build_session_plan(config: ToolConfig, state: dict, *, now: datetime | None = None, seed: str | None = None) -> SessionPlan:
    current = now or datetime.now()
    resolved_seed = seed or current.strftime("%Y-%m-%d")
    rng = random.Random(resolved_seed)

    resolved_targets = resolve_targets(config)
    if config.session.visit_mode == "current_profile_sidebar":
        visits = _build_current_profile_sidebar_visits(config, rng)
    else:
        visits = _build_explicit_target_visits(config, rng)

    candidates = build_message_target_candidates(config, resolved_targets)
    message_target = next_message_target(config, state, candidates=candidates)
    drafts = next_message_drafts(config, state) if message_target is not None else []
    return SessionPlan(
        seed=resolved_seed,
        visits=visits,
        message_target_username=message_target.username() if message_target is not None else "",
        message_target_uri=message_target.uri() if message_target is not None else "",
        message_drafts=drafts,
    )
