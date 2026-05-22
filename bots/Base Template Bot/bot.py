"""
Template Bot — Reference Bot 1

Strategy: Play pocket pairs and strong broadway hands. Call only when pot odds justify it.

"""


"""
CARD FORMAT:
Cards are strings like "As" (Ace of spades), "Td" (Ten of diamonds)
Ranks: 2 3 4 5 6 7 8 9 T J Q K A
Suits: s (spades) h (hearts) d (diamonds) c (clubs)

RETURN FORMAT:
{"action": "fold"}
{"action": "check"}          # only valid when amount_owed == 0
{"action": "call"}
{"action": "raise", "amount": 1200}   # amount = TOTAL bet, not raise-by
{"action": "all_in"}

Invalid actions default to fold. Raises below min_raise_to are snapped up.
"""

# ── You can add imports here ──────────────────────────────────────────────────
import random
# ─────────────────────────────────────────────────────────────────────────────

BOT_NAME = "Template"
BOT_AVATAR = "GentleLion"


STRONG_PAIRS   = {"AA", "KK", "QQ", "JJ", "TT"}
MEDIUM_PAIRS   = {"99", "88", "77", "66"}
BROADWAY_HANDS = {"AK", "AQ", "AJ", "KQ"}

def _hand_label(cards):
    """Return a two label like 'AA', 'AK', 'J8' from hole cards"""
    rank_order = "23456789TJQKA"
    r1, r2 = cards[0][0], cards[1][0]
    if rank_order.index(r1) < rank_order.index(r2):
        r1, r2 = r2, r1
    return r1 + r2


def decide(game_state: dict) -> dict:
    """
    Called once per action. Must return within 2 seconds.

    game_state keys:
    hand_id          str   — unique hand identifier
    street           str   — "preflop" | "flop" | "turn" | "river"
    seat_to_act      int   — your seat number (0-5)
    pot              int   — total chips in pot
    community_cards  list  — e.g. ["As", "Kd", "7h"] (empty preflop)
    current_bet      int   — highest bet on this street
    min_raise_to     int   — minimum legal raise total
    amount_owed      int   — chips you need to put in to call (0 = free check)
    can_check        bool  — True when amount_owed == 0
    your_cards       list  — your two hole cards, e.g. ["Ah", "Kh"]
    your_stack       int   — your remaining chips
    your_bet_this_street int — chips you've already put in this street
    players          list  — public info on all seats (see below)
    action_log       list  — all actions so far this hand

    players[i] keys (public info only, no hole cards):
    seat, bot_id, stack, is_active, is_folded, is_all_in, bet_this_street
    """

    # ── Your strategy goes here ───────────────────────────────────────────────
    hand = _hand_label(game_state["your_cards"])
    pot = game_state["pot"]
    owed = game_state["amount_owed"]


### PRE-FLOP
    if game_state["street"] == "preflop":
        if hand in STRONG_PAIRS:
            return {"action": "raise", "amount": game_state["min_raise_to"] * 3}
        
        if hand in MEDIUM_PAIRS or hand in BROADWAY_HANDS:
            if owed == 0:
                return {"action": "check"}
            if owed <= pot * 0.25:
                return {"action": "call"}
            
        if owed == 0:
            return {"action", "check"}
        
        return {"action": "fold"}
    

### POST-FLOP: Pot Odds
    if owed == 0:
        return {"action": "check"}
    
    pot_odds = owed / (pot + owed) if (pot + owed) > 0 else 1.0
    if pot_odds <= 0.25:                # getting 3:1 or better
        return {"action": "call"}
    
    return {"action": "fold"}

















    # ─────────────────────────────────────────────────────────────────────────
