"""
Bot A: The Aggressor - raises constantly, bets big.

Never Fold, Never Call -> Always Raise or go All-In
"""

import random

BOT_NAME = "The Aggressor"

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

def decide(state):
    """
    Called once per action. Must return within 2 seconds.

    game_state keys:
    hand_id          str   - unique hand identifier
    street           str   - "preflop" | "flop" | "turn" | "river"
    seat_to_act      int   - your seat number (0-5)
    pot              int   - total chips in pot
    community_cards  list  - e.g. ["As", "Kd", "7h"] (empty preflop)
    current_bet      int   - highest bet on this street
    min_raise_to     int   - minimum legal raise total
    amount_owed      int   - chips you need to put in to call (0 = free check)
    can_check        bool  - True when amount_owed == 0
    your_cards       list  - your two hole cards, e.g. ["Ah", "Kh"]
    your_stack       int   - your remaining chips
    your_bet_this_street int - chips you've already put in this street
    players          list  - public info on all seats (see below)
    action_log       list  - all actions so far this hand

    players[i] keys (public info only, no hole cards):
    seat, bot_id, stack, is_active, is_folded, is_all_in, bet_this_street
    """


    min_raise = state.get("min_raise_to", 0)
    stack = state["your_stack"]

    if min_raise > 0 and min_raise <= stack:
        # Raise to 2X the value
        amount = min(min_raise*2, stack)
        return {"action": "raise", "amount": amount}
    
    if stack > 0:
        return {"action": "all_in"}
    
    return {"action": "call"}
    