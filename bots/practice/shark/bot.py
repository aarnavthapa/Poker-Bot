"""
Bot: The Shark 

Strategy: tight preflop, position-aware, value bets.
"""
import random

BOT_NAME = "The Shark"

# Hand categories (suited treated as bonus — not tracked here for simplicity)
PREMIUM   = {"AA", "KK", "QQ", "AK"}
STRONG    = {"JJ", "TT", "AQ", "AJ", "KQ"}
PLAYABLE  = {"99", "88", "77", "AT", "KJ", "QJ", "JT"}

RANK_ORDER = "23456789TJQKA"

def _rank(c):
    return RANK_ORDER.index(c[0])

def _hand_label(cards):
    r1, r2 = cards[0][0], cards[1][0]
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2 = r2, r1
    return r1 + r2

def _is_suited(cards):
    return cards[0][1] == cards[1][1]


def _position(state):
    """
    Determine rough position from action_log.
    Returns 'early', 'middle', or 'late'.
    Players acting later have more info — widen range.
    """
    players = state.get("players", [])
    n = len(players)
    if n <= 2:
        return "late"
    # Find our seat index by looking at whose turn it was last
    # Simple heuristic: use players list order
    for i, p in enumerate(players):
        if p.get("is_you"):
            if i < n // 3:
                return "early"
            elif i < 2 * n // 3:
                return "middle"
            else:
                return "late"
    return "middle"

def _high_card_strength(cards):
    """Simple 0-1 score based on hole card ranks."""
    r1, r2 = _rank(cards[0]), _rank(cards[1])
    return (r1 + r2) / 24.0   # max = 12+12 = 24



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


    hand = _hand_label(state["your_cards"])
    suited = _is_suited(state["your_cards"])
    street = state["street"]
    pot = state["pot"]
    owed = state["amount_owed"]
    stack = state["your_stack"]
    min_raise = state.get("min_raise_to", owed * 2)
    position = _position(state)

    # PRE-FLOP
    if street == "preflop":
        if hand in PREMIUM:
            # Always raise a premium hand
            raise_to = min(min_raise*2, stack)
            return {"action": "raise", "amount": raise_to}
        
        if hand in STRONG:
            if position in ("middle", "late"):
                raise_to = min(min_raise, stack)
                return {"action": "raise", "amount": raise_to}
            
            if owed == 0:
                return {"action": "check"}
            
            if owed <= pot * 0.15:
                return {"action": "call"}
            
            return {"action": "fold"}
        
        if hand in PLAYABLE or (suited and _high_card_strength(state["your_cards"]) > 0.6):
            if position == "late":
                if owed == 0:
                    return {"action": "check"}
                if owed <= pot * 0.12:
                    return {"action": "call"}
            if owed == 0:
                return {"action": "check"}
            return {"action": "fold"}

        if owed == 0:
            return {"action": "check"}
        return {"action": "fold"}


    # POST-FLOP
    community = state.get("community_cards", [])
    hc = _high_card_strength(state["your_cards"])


    # Calculating board-connection score
    our_ranks = {state["your_cards"][0][0], state["your_cards"[1][0]]}
    board_ranks = {c[0] for c in community}
    pairs_on_board = len(board_ranks) < len(community)  # duplicate rank = pair on board
    connected = len(our_ranks & board_ranks)            # how many hole cards hit the board

    if owed == 0:
            # Bet for value when we have something
            if connected >= 1 or hc > 0.75:
                bet = max(int(pot * 0.5), min_raise)
                if bet <= stack:
                    return {"action": "raise", "amount": bet}
            return {"action": "check"}
    
    # Calling/Folding decision - 
    pot_odds = owed / (owed + pot) if (pot + owed) > 0 else 1

    if connected >= 2:                                 # Two Pair or better
        if pot_odds <= 0.5:
            return {"action": "call"}
        
    elif connected == 1:                               # One pair
        if pot_odds <= 0.3:
            return {"action": "call"}
    
    else:
        if pot_odds <= 0.20:                           # Only call very cheap with overcards
            return {"action": "call"}
        
    return {"action": "fold"}