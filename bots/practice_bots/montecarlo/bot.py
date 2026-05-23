"""
Monte Carlo Bot — treys edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Uses the `treys` library instead of eval7.
Same Monte Carlo logic — only the hand evaluation layer is different.

Install:
    pip install treys

Key treys differences from eval7
──────────────────────────────────
eval7:   eval7.Card("As")                → card object
treys:   Card.new("As")                  → card integer

eval7:   eval7.evaluate(list_of_7_cards) → score (lower = better)
treys:   Evaluator().evaluate(board, hole) → score (lower = better)
        board = 3–5 card ints
        hole  = exactly 2 card ints

Both use the same scoring convention: LOWER integer = STRONGER hand.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import random
from treys import Card, Evaluator

# ─────────────────────────────────────────────────────────────────────────────
# INITIALISE ONCE AT IMPORT TIME (not inside decide — that would be slow)
# ─────────────────────────────────────────────────────────────────────────────

# Single evaluator instance reused every call
EVALUATOR = Evaluator()

# Pre-build the full 52-card deck as treys card integers
# treys uses bit-field integers internally — Card.new() converts a string once
FULL_DECK = [Card.new(r + s) for r in "23456789TJQKA" for s in "shdc"]

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

MC_SAMPLES       = 500   # simulations per decision (~100–150 ms on most laptops)
DRAW_BONUS       = 0.08  # implied equity bonus for flush/straight draws
RIVER_BLUFF_FREQ = 0.20  # how often we bluff with nothing on the river
SEMI_BLUFF_FREQ  = 0.60  # how often we semi-bluff with a draw

# ─────────────────────────────────────────────────────────────────────────────
# PREFLOP HAND RANGES
# ─────────────────────────────────────────────────────────────────────────────

OPEN_RAISE_EARLY = {
    "AA","KK","QQ","JJ","TT",
    "AK","AQ","AJ","KQ",
}
OPEN_RAISE_MIDDLE = OPEN_RAISE_EARLY | {
    "99","88","77",
    "AT","KJ","QJ","JTs","T9s",
}
OPEN_RAISE_LATE = OPEN_RAISE_MIDDLE | {
    "66","55","44","33","22",
    "A9","A8","A7","A6","A5","A4","A3","A2",
    "K9","K8","Q9","J9","T8","98","87","76","65","54",
}
FOUR_BET_HANDS = {"AA","KK","QQ","AK"}
CALL_3BET_HANDS = {"JJ","TT","AQ","AJ","KQ"}

# ─────────────────────────────────────────────────────────────────────────────
# CARD UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

RANK_ORDER = "23456789TJQKA"

def rank_value(card_str: str) -> int:
    """'As' → 12,  '2h' → 0"""
    return RANK_ORDER.index(card_str[0])

def is_suited(hole: list) -> bool:
    return hole[0][1] == hole[1][1]

def hand_label(hole: list) -> str:
    """
    Returns a 2-char label for range lookups.
    Always higher rank first: hand_label(['2s','Ah']) → 'A2'
    """
    r1, r2 = hole[0][0], hole[1][0]
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2 = r2, r1
    return r1 + r2

# ─────────────────────────────────────────────────────────────────────────────
# DRAW DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def has_flush_draw(hole: list, board: list) -> bool:
    """True if we have 4 cards of the same suit (one away from a flush)."""
    suit_counts = {}
    for c in hole + board:
        s = c[1]
        suit_counts[s] = suit_counts.get(s, 0) + 1
    return any(v == 4 for v in suit_counts.values())

def has_straight_draw(hole: list, board: list) -> bool:
    """True if we have 4 cards in a 5-rank window (open-ended or gutshot)."""
    ranks = sorted(set(rank_value(c) for c in hole + board))
    for i in range(len(ranks) - 3):
        if ranks[i + 3] - ranks[i] <= 4:
            return True
    return False

def has_draw(hole: list, board: list) -> bool:
    return has_flush_draw(hole, board) or has_straight_draw(hole, board)

# ─────────────────────────────────────────────────────────────────────────────
# POSITION & OPPONENT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_position(players: list) -> str:
    n = max(len(players), 1)
    for i, p in enumerate(players):
        if p.get("is_you"):
            frac = i / n
            if frac < 0.33:   return "early"
            elif frac < 0.67: return "middle"
            else:             return "late"
    return "middle"

def active_opponents(players: list) -> int:
    return max(
        sum(1 for p in players
            if not p.get("is_you")
            and not p.get("folded", False)
            and p.get("stack", 1) > 0),
        1
    )

def opponent_aggression(action_log: list) -> float:
    """0 = passive rock, 1 = total maniac."""
    aggressive, total = 0, 0
    for entry in action_log[-40:]:
        if entry.get("is_you"):
            continue
        action = entry.get("action", "")
        if action in ("raise", "all_in"):
            aggressive += 1
        if action not in ("", "blind", "post"):
            total += 1
    return aggressive / total if total > 0 else 0.5

def spr(stack: int, pot: int) -> float:
    return stack / max(pot, 1)

# ─────────────────────────────────────────────────────────────────────────────
# MONTE CARLO EQUITY  — treys version
# ─────────────────────────────────────────────────────────────────────────────

def monte_carlo_equity(
    hole_strings: list,
    board_strings: list,
    num_players: int,
    samples: int = MC_SAMPLES
) -> float:
    """
    Estimate win probability via random board runout simulations.

    Parameters
    ──────────
    hole_strings   : our 2 hole cards as strings  e.g. ['As', 'Kh']
    board_strings  : current board cards          e.g. ['7d', 'Tc', '2s']
    num_players    : us + active opponents
    samples        : how many simulations to run

    How treys evaluation works here
    ────────────────────────────────
    treys.Evaluator.evaluate(board, hand) needs:
    • board : list of 3–5 card ints  (we always complete to 5)
    • hand  : list of exactly 2 card ints

    Both arguments use the integer format from Card.new().
    Lower integer score = stronger hand.  Same convention as eval7.

    Returns
    ───────
    Float 0.0–1.0 representing our equity (win rate).
    """
    try:
        # Convert our known cards to treys integers
        hole_ints  = [Card.new(c) for c in hole_strings]
        board_ints = [Card.new(c) for c in board_strings]
        known      = set(hole_ints + board_ints)

        # Build the remaining deck (exclude cards we can already see)
        remaining = [c for c in FULL_DECK if c not in known]

        cards_needed_on_board = 5 - len(board_strings)
        num_opponents         = num_players - 1
        cards_per_deal        = num_opponents * 2 + cards_needed_on_board

        wins  = 0
        total = 0

        for _ in range(samples):
            if len(remaining) < cards_per_deal:
                break  # not enough cards (rare edge case)

            random.shuffle(remaining)
            idx = 0

            # Deal 2 cards to each opponent
            opp_hands = []
            for _ in range(num_opponents):
                opp_hands.append(remaining[idx:idx + 2])
                idx += 2

            # Complete the board
            runout     = remaining[idx:idx + cards_needed_on_board]
            full_board = board_ints + runout  # always 5 cards total

            # ── treys evaluation ────────────────────────────────────────────
            # evaluate(board, hand)  →  lower score = better hand
            my_score = EVALUATOR.evaluate(full_board, hole_ints)

            best_opp_score = None
            for opp in opp_hands:
                s = EVALUATOR.evaluate(full_board, opp)
                if best_opp_score is None or s < best_opp_score:
                    best_opp_score = s

            if my_score < best_opp_score:
                wins += 1
            elif my_score == best_opp_score:
                wins += 0.5   # split pot

            total += 1

        return wins / total if total > 0 else 0.5

    except Exception:
        return 0.5   # safe fallback — never crash the bot

# ─────────────────────────────────────────────────────────────────────────────
# BETTING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def pot_odds_required(owed: int, pot: int) -> float:
    """Minimum equity needed to break even on a call."""
    total = pot + owed
    return owed / total if total > 0 else 1.0

def build_raise(state: dict, pot_fraction: float) -> dict:
    """Raise to pot_fraction × pot. Respects min_raise and stack."""
    pot      = state["pot"]
    stack    = state["your_stack"]
    min_r    = state.get("min_raise_to", state["amount_owed"] * 2)
    amount   = max(int(pot * pot_fraction), min_r)
    amount   = min(amount, stack)
    if amount >= stack:
        return {"action": "all_in"}
    return {"action": "raise", "amount": amount}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def decide(state: dict) -> dict:
    """Called by the engine once per action. Must return within 2 seconds."""

    # ── Unpack state ─────────────────────────────────────────────────────────
    hole       = state["your_cards"]
    board      = state.get("community_cards", [])
    street     = state["street"]
    pot        = state["pot"]
    owed       = state["amount_owed"]
    stack      = state["your_stack"]
    can_check  = state.get("can_check", owed == 0)
    players    = state.get("players", [])
    log        = state.get("action_log", [])

    label      = hand_label(hole)
    suited     = is_suited(hole)
    position   = get_position(players)
    n_opps     = active_opponents(players)
    n_players  = n_opps + 1
    opp_agg    = opponent_aggression(log)
    stack_pot  = spr(stack, pot)

    # ═══════════════════════════════════════════════════════════════════════════
    # PREFLOP — hand range tables (no Monte Carlo needed here)
    # ═══════════════════════════════════════════════════════════════════════════
    if street == "preflop":

        if position == "early":
            my_range = OPEN_RAISE_EARLY
        elif position == "middle":
            my_range = OPEN_RAISE_MIDDLE
        else:
            my_range = OPEN_RAISE_LATE

        in_range = label in my_range or (suited and (label + "s") in my_range)

        if owed > 0:
            # Facing a raise
            if label in FOUR_BET_HANDS:
                return build_raise(state, 4.0)
            if label in CALL_3BET_HANDS:
                return {"action": "call"}
            high = max(rank_value(hole[0]), rank_value(hole[1]))
            if suited and high >= 8 and n_opps >= 2 and owed <= pot * 0.15:
                return {"action": "call"}
            if in_range and owed <= pot * 0.20:
                return {"action": "call"}
            return {"action": "fold"}

        # No raise to face
        if in_range:
            return build_raise(state, 2.5)
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # ═══════════════════════════════════════════════════════════════════════════
    # POST-FLOP — Monte Carlo equity estimation
    # ═══════════════════════════════════════════════════════════════════════════

    equity  = monte_carlo_equity(hole, board, n_players, MC_SAMPLES)
    drawing = has_draw(hole, board) and street != "river"

    # Adjust equity threshold based on opponent style
    # vs. maniac (high aggression): widen calls — they bluff a lot
    # vs. rock (low aggression):    tighten calls — they have it when they bet
    aggression_adj = 0.05 - (opp_agg * 0.10)   # ranges ±0.05

    # SPR-based commit threshold
    # Low SPR = we're already deep in the pot, lower bar to shove
    if stack_pot < 2:
        commit_threshold = 0.52
    elif stack_pot < 4:
        commit_threshold = 0.58
    elif stack_pot < 8:
        commit_threshold = 0.65
    else:
        commit_threshold = 0.72

    # ── Facing a bet ──────────────────────────────────────────────────────────
    if owed > 0:
        required     = pot_odds_required(owed, pot)
        eff_equity   = equity + (DRAW_BONUS if drawing else 0) - aggression_adj

        # Near pot-committed with a strong hand → shove
        if eff_equity >= commit_threshold and stack_pot < 3:
            return {"action": "all_in"}

        # Clear edge over pot odds → call or raise
        if eff_equity >= required + 0.05:
            if equity >= 0.72 and owed < pot * 0.6:
                return build_raise(state, 1.0)   # value raise
            return {"action": "call"}

        # Barely breakeven but with a live draw → call for implied odds
        if drawing and eff_equity >= required:
            return {"action": "call"}

        return {"action": "fold"}

    # ── We act first (no bet to face) ────────────────────────────────────────
    if not can_check:
        return {"action": "fold"}

    if equity >= 0.72:
        # Strong hand: value bet
        frac = 0.5 if stack_pot > 6 else 0.75
        return build_raise(state, frac)

    if equity >= 0.58:
        # Medium strength: protection/value bet
        return build_raise(state, 0.5)

    if drawing:
        # Semi-bluff: we might win now OR hit our draw later
        if random.random() < SEMI_BLUFF_FREQ:
            return build_raise(state, 0.6)
        return {"action": "check"}

    if street == "river" and equity < 0.35:
        # Pure bluff with air — low frequency
        if random.random() < RIVER_BLUFF_FREQ:
            return build_raise(state, 0.65)

    return {"action": "check"}