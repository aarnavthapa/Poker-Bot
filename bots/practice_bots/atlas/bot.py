"""
Atlas Bot — Competition Entry - Currently uses eval7
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategy overview
─────────────────
Preflop   : GTO-inspired range, position-adjusted open-raises and 3-bets
Postflop  : Monte-Carlo equity estimation via eval7, SPR-aware sizing,
            c-bet / double-barrel / check-raise logic
Bluffing  : Semi-bluffs on draws, small frequency pure bluffs on river
Exploit   : Detects passive / aggressor opponent patterns from action_log
            and adjusts calling range / bet sizing accordingly

Constraints respected
─────────────────────
✓  No network calls
✓  No file I/O during gameplay
✓  eval7 / numpy only (both in requirements.txt)
✓  Runs in << 2 seconds (MC sims capped at SAMPLES iterations)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import random
import eval7

# ── Tuneable constants ────────────────────────────────────────────────────────
SAMPLES        = 400   # Monte-Carlo equity samples (keeps us well under 2 s)
C_BET_FREQ     = 0.70  # How often we c-bet when checked to as preflop raiser
BLUFF_RIVER_FREQ = 0.25  # Pure bluff frequency on river (no equity)

# ── Preflop hand ranges ───────────────────────────────────────────────────────
# Each set contains 2-char hand labels (e.g. "AK" = AKo+AKs combined)
OPEN_RAISE_EP = {                     # Early position — very tight
    "AA","KK","QQ","JJ","TT",
    "AK","AQ","AJ","KQ",
}
OPEN_RAISE_MP = OPEN_RAISE_EP | {    # Middle position — add medium pairs + suited broadways
    "99","88","77",
    "AT","KJ","QJ","JTs","T9s",
}
OPEN_RAISE_LP = OPEN_RAISE_MP | {    # Late / button — wide
    "66","55","44","33","22",
    "A9","A8","A7","A6","A5","A4","A3","A2",
    "K9","K8","Q9","Q8","J9","T8","98","87","76","65","54",
}
CALL_3BET = {"AA","KK","QQ","JJ","TT","AK","AQ"}
FOUR_BET  = {"AA","KK","QQ","AK"}

# ── Rank helpers ─────────────────────────────────────────────────────────────
RANK_ORDER = "23456789TJQKA"

def _rank_val(c: str) -> int:
    return RANK_ORDER.index(c[0])

def _hand_label(cards) -> str:
    r1, r2 = cards[0][0], cards[1][0]
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2 = r2, r1
    label = r1 + r2
    # Mark suited
    if cards[0][1] == cards[1][1]:
        label += "s"
    return label

def _hand_label_base(cards) -> str:
    """2-char label without suited marker for range lookups."""
    return _hand_label(cards)[:2]

def _is_suited(cards) -> bool:
    return cards[0][1] == cards[1][1]

# ── eval7 helpers ─────────────────────────────────────────────────────────────

def _to_eval7(card_str: str) -> eval7.Card:
    return eval7.Card(card_str)

def _monte_carlo_equity(hole_cards, community_cards, num_players: int, samples: int) -> float:
    """
    Run Monte-Carlo equity estimation.
    Returns win probability [0, 1] for our hand against (num_players-1) random opponents.
    """
    try:
        deck = eval7.Deck()
        known = [_to_eval7(c) for c in hole_cards + community_cards]
        deck.cards = [c for c in deck.cards if c not in known]

        wins = 0
        needed_board = 5 - len(community_cards)
        community_e7 = [_to_eval7(c) for c in community_cards]
        hole_e7      = [_to_eval7(c) for c in hole_cards]

        for _ in range(samples):
            random.shuffle(deck.cards)
            idx = 0
            opp_holes = []
            for _ in range(num_players - 1):
                opp_holes.append(deck.cards[idx:idx+2])
                idx += 2
            runout = deck.cards[idx:idx+needed_board]
            board  = community_e7 + runout

            my_score = eval7.evaluate(hole_e7 + board)
            best_opp = min(eval7.evaluate(o + board) for o in opp_holes)
            # eval7: lower score = better hand
            if my_score < best_opp:
                wins += 1
            elif my_score == best_opp:
                wins += 0.5

        return wins / samples
    except Exception:
        return 0.5  # safe fallback

# ── Draw detection ────────────────────────────────────────────────────────────

def _flush_draw(hole, board) -> bool:
    """True if we have 4 to a flush."""
    all_cards = hole + board
    suit_counts = {}
    for c in all_cards:
        s = c[1]
        suit_counts[s] = suit_counts.get(s, 0) + 1
    return any(v >= 4 for v in suit_counts.values())

def _straight_draw(hole, board) -> bool:
    """True if we have an open-ended or gutshot straight draw."""
    ranks = sorted(set(_rank_val(c) for c in hole + board))
    for i in range(len(ranks) - 3):
        span = ranks[i+3] - ranks[i]
        if span <= 4:
            return True
    return False

def _has_draw(hole, board) -> bool:
    return _flush_draw(hole, board) or _straight_draw(hole, board)

# ── Position detection ────────────────────────────────────────────────────────

def _position(state) -> str:
    """Returns 'early', 'middle', or 'late'."""
    players = state.get("players", [])
    n = max(len(players), 1)
    for i, p in enumerate(players):
        if p.get("is_you"):
            if i < n // 3:
                return "early"
            elif i < 2 * n // 3:
                return "middle"
            else:
                return "late"
    return "middle"

# ── Opponent profiling ────────────────────────────────────────────────────────

def _opponent_aggression(state) -> float:
    """
    0.0 = very passive, 1.0 = very aggressive.
    Computed from recent action_log entries by non-hero players.
    """
    log = state.get("action_log", [])
    aggressive = 0
    total = 0
    for entry in log[-30:]:           # last 30 actions
        if entry.get("is_you"):
            continue
        action = entry.get("action", "")
        if action in ("raise", "all_in"):
            aggressive += 1
        if action not in ("", "blind"):
            total += 1
    if total == 0:
        return 0.5
    return aggressive / total

def _num_active_opponents(state) -> int:
    players = state.get("players", [])
    active = sum(
        1 for p in players
        if not p.get("is_you") and not p.get("folded") and p.get("stack", 1) > 0
    )
    return max(active, 1)

# ── Stack-to-pot ratio ────────────────────────────────────────────────────────

def _spr(state) -> float:
    pot = max(state["pot"], 1)
    return state["your_stack"] / pot

# ── Betting helpers ───────────────────────────────────────────────────────────

def _raise_to(state, fraction: float) -> dict:
    """Raise to fraction of pot. Respects min raise and stack."""
    pot      = state["pot"]
    stack    = state["your_stack"]
    min_r    = state.get("min_raise_to", state["amount_owed"] * 2)
    amount   = max(int(pot * fraction), min_r)
    amount   = min(amount, stack)
    if amount >= stack:
        return {"action": "all_in"}
    return {"action": "raise", "amount": amount}

def _call_or_fold(state, equity: float) -> dict:
    """Call if equity justifies it, otherwise fold."""
    owed     = state["amount_owed"]
    pot      = state["pot"]
    total    = pot + owed
    required = owed / total if total > 0 else 1.0  # pot odds
    if equity >= required:
        return {"action": "call"}
    return {"action": "fold"}

# ── Main decide function ──────────────────────────────────────────────────────

def decide(state: dict) -> dict:
    hole      = state["your_cards"]
    board     = state.get("community_cards", [])
    street    = state["street"]
    pot       = state["pot"]
    owed      = state["amount_owed"]
    stack     = state["your_stack"]
    can_check = state.get("can_check", owed == 0)
    min_raise = state.get("min_raise_to", owed * 2)
    position  = _position(state)
    spr       = _spr(state)
    opp_agg   = _opponent_aggression(state)
    n_opps    = _num_active_opponents(state)

    label      = _hand_label_base(hole)
    is_suited  = _is_suited(hole)

    # ═══════════════════════════════════════════════════════════════════════════
    # PREFLOP
    # ═══════════════════════════════════════════════════════════════════════════
    if street == "preflop":
        # Choose open-raise range by position
        if position == "early":
            raise_range = OPEN_RAISE_EP
        elif position == "middle":
            raise_range = OPEN_RAISE_MP
        else:
            raise_range = OPEN_RAISE_LP

        in_range = label in raise_range or (is_suited and label + "s" in raise_range)

        # ── Facing a raise (we owe chips) ─────────────────────────────────────
        if owed > 0:
            # 3-bet or 4-bet logic
            if label in FOUR_BET:
                return _raise_to(state, 4.0)   # 4-bet to 4× pot
            if label in CALL_3BET:
                return {"action": "call"}
            # Suited connectors / speculative hands with good implied odds
            if is_suited and _rank_val(hole[0]) >= 8 and _rank_val(hole[1]) >= 6:
                if owed <= pot * 0.15 and n_opps >= 2:
                    return {"action": "call"}
            if in_range and owed <= pot * 0.20:
                return {"action": "call"}
            return {"action": "fold"}

        # ── No bet to face — open action ──────────────────────────────────────
        if in_range:
            # Raise to 2.5BB equivalent (approximate: 2.5× min raise)
            return _raise_to(state, 2.5)

        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # ═══════════════════════════════════════════════════════════════════════════
    # POST-FLOP  (flop / turn / river)
    # ═══════════════════════════════════════════════════════════════════════════

    # Run equity estimation
    equity = _monte_carlo_equity(hole, board, n_opps + 1, SAMPLES)
    draw   = _has_draw(hole, board)

    # Adjust equity estimate for draws on later streets
    # On river there are no more cards — draw value = 0
    if street == "river" and draw:
        draw = False   # draw didn't complete → evaluate as made hand only

    # ── SPR-based commitment threshold ────────────────────────────────────────
    # Low SPR (<3): commit with any equity advantage — all-in is fine
    # High SPR (>10): need strong equity to get stacks in
    commit_threshold = 0.55 if spr < 3 else 0.65 if spr < 6 else 0.70

    # ── Facing a bet ──────────────────────────────────────────────────────────
    if owed > 0:
        pot_odds   = owed / (pot + owed)
        draw_bonus = 0.10 if draw else 0.0   # draws get extra implied odds equity credit
        eff_equity = equity + draw_bonus

        if eff_equity >= commit_threshold and spr < 3:
            # Happy to get all the chips in
            return {"action": "all_in"}

        if eff_equity >= pot_odds + 0.05:    # need a 5% edge over raw pot odds to call
            # Consider raising for value
            if equity >= 0.70 and owed < pot * 0.5:
                return _raise_to(state, 1.0)
            return {"action": "call"}

        if draw and street != "river":
            # Pure pot odds + implied odds for draws
            implied_odds = owed / (pot + owed + stack * 0.3)  # estimate future value
            if implied_odds <= equity + 0.05:
                return {"action": "call"}

        # Fold — not getting the right price
        return {"action": "fold"}

    # ── No bet to face — we act first ─────────────────────────────────────────
    if can_check:
        # Decide whether to bet or check
        if equity >= 0.70:
            # Strong hand: value bet
            bet_frac = 0.75 if spr > 4 else 0.5  # bigger bets in deep play
            return _raise_to(state, bet_frac)

        if equity >= 0.55:
            # Medium strength: bet for value/protection, half pot
            return _raise_to(state, 0.5)

        if draw and street != "river":
            # Semi-bluff: bet with a draw to fold out better hands or build pot
            if random.random() < 0.55:         # semi-bluff 55% of the time
                return _raise_to(state, 0.6)
            return {"action": "check"}

        if street == "river" and equity < 0.35:
            # River bluff with pure air — low frequency
            if random.random() < BLUFF_RIVER_FREQ:
                return _raise_to(state, 0.7)

        # Weak hand / missed draw — check to control pot
        return {"action": "check"}

    # Fallback (should not reach here)
    return {"action": "fold"}