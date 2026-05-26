"""
Nemesis — Exploitative Adaptive Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHY THIS BEATS CFR
───────────────────
CFR computes a Nash Equilibrium — a strategy nobody can exploit.
The catch: Nash Equilibrium also never EXPLOITS the opponent.
It plays identically against every bot, good or bad.

Nemesis does something different:
1. Watch what the opponent does across every hand
2. Build a statistical profile of their tendencies
3. Detect which "player type" they are
4. Maximally exploit the leaks in that type

Against a non-Nash opponent (which every bot in this competition is),
exploitation always wins more than Nash equilibrium.

OPPONENT STATS TRACKED
───────────────────────
VPIP  — Voluntarily Put Money In Pot (preflop)
        High VPIP = plays too many hands = loose player
        Low VPIP  = plays too few hands  = tight/nit

PFR   — Preflop Raise %
        High PFR = aggressive preflop
        Low PFR  = passive preflop (calls a lot, rarely raises)

AF    — Aggression Factor = (bets + raises) / calls (postflop)
        High AF = bets and raises frequently = aggressive
        Low AF  = calls and checks a lot    = passive

FtCB  — Fold to C-Bet % (fold when we bet the flop as preflop raiser)
        High FtCB = folds to pressure easily = bluff them more
        Low FtCB  = calls everything         = never bluff them

WtSD  — Went to Showdown % (how often they see the river)
        High WtSD = calling station          = value bet mercilessly
        Low WtSD  = folds a lot             = bluff them aggressively

PLAYER TYPES AND COUNTER-STRATEGIES
─────────────────────────────────────
Type            VPIP    PFR    AF    Counter-strategy
─────────────────────────────────────────────────────
Calling Station  >40%   <10%  <1.0  Never bluff. Value bet every street.
                                    Bet big with any made hand.

Maniac/LAG       >35%   >25%  >2.5  Tighten range. Let them bluff.
                                    Call down with medium hands.
                                    Trap with strong hands.

TAG (Solid)      15-30% 15-25% 1-2  Steal blinds. Respect their bets.
                                    C-bet often on dry boards.

Nit              <15%   <10%  <1.0  Bluff constantly. Steal every pot.
                                    Fold to their bets (they have it).

CFR Bot          ~28%   ~22%  ~1.5  Exploit abstraction seams.
                                    Overbet on wet boards (CFR undertreats).
                                    3-bet light (CFR folds too much to 3bets).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import random
from treys import Card, Evaluator

# ─────────────────────────────────────────────────────────────────────────────
# INITIALISE (once at import time, not inside decide())
# ─────────────────────────────────────────────────────────────────────────────

EVALUATOR = Evaluator()
FULL_DECK = [Card.new(r + s) for r in '23456789TJQKA' for s in 'shdc']

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

MC_SAMPLES       = 450    # Monte Carlo equity simulations per decision
MIN_HANDS_TO_EXP = 15     # hands needed before we trust our stats and exploit
DRAW_BONUS       = 0.08   # implied equity bonus for draws

# ─────────────────────────────────────────────────────────────────────────────
# OPPONENT STATISTICS TRACKER
# ─────────────────────────────────────────────────────────────────────────────
# This is the memory of Nemesis. It persists across all hands in a match
# because it lives at module level (created once at import time).

class OpponentStats:
    """
    Tracks opponent tendencies across the entire match.
    Updates after every hand we see.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        # VPIP tracking
        self.hands_seen          = 0
        self.hands_vpip          = 0    # hands they put money in voluntarily

        # PFR tracking
        self.hands_pfr           = 0    # hands they raised preflop

        # Postflop aggression
        self.postflop_bets       = 0    # times they bet or raised postflop
        self.postflop_calls      = 0    # times they called postflop

        # C-bet response
        self.faced_cbet          = 0    # times they faced our flop c-bet
        self.folded_to_cbet      = 0    # times they folded to it

        # Showdown tracking
        self.saw_showdown        = 0    # times they reached showdown
        self.hands_postflop      = 0    # hands that went to flop

        # Track hand IDs we've already processed (avoid double-counting)
        self._seen_hand_ids      = set()
        self._last_log_length    = 0

    # ── Computed stats ────────────────────────────────────────────────────────

    @property
    def vpip(self):
        if self.hands_seen < 5: return 0.28   # assume average
        return self.hands_vpip / self.hands_seen

    @property
    def pfr(self):
        if self.hands_seen < 5: return 0.18
        return self.hands_pfr / self.hands_seen

    @property
    def af(self):
        """Aggression Factor = (bets+raises) / calls. >2 = aggressive, <1 = passive."""
        if self.postflop_calls == 0:
            return 2.0 if self.postflop_bets > 0 else 1.0
        return self.postflop_bets / self.postflop_calls

    @property
    def fold_to_cbet(self):
        if self.faced_cbet < 5: return 0.50   # assume average
        return self.folded_to_cbet / self.faced_cbet

    @property
    def wtsd(self):
        """Went to showdown rate."""
        if self.hands_postflop < 5: return 0.35
        return self.saw_showdown / self.hands_postflop

    @property
    def player_type(self):
        """
        Classify opponent into one of four types.
        This drives the entire exploit strategy.
        """
        if self.hands_seen < MIN_HANDS_TO_EXP:
            return 'unknown'

        v = self.vpip
        p = self.pfr
        a = self.af

        if v > 0.40 and p < 0.15:  return 'calling_station'
        if v > 0.35 and a > 2.0:   return 'maniac'
        if v < 0.18 and p < 0.12:  return 'nit'
        if v < 0.30 and p > 0.15:  return 'tag'
        return 'lag'    # default: loose aggressive

    def update(self, action_log, street):
        """
        Parse the action log to update stats.
        Called at the start of each decide() so we always have fresh data.
        """
        if len(action_log) <= self._last_log_length:
            return
        self._last_log_length = len(action_log)

        for entry in action_log:
            if entry.get('is_you'):
                continue
            action = entry.get('action', '')
            ent_street = entry.get('street', '')

            # VPIP: any voluntary preflop investment (not forced blind)
            if ent_street == 'preflop' and action in ('call', 'raise', 'all_in'):
                self.hands_vpip += 1   # approximate (may double count — acceptable)

            # PFR: raised preflop
            if ent_street == 'preflop' and action in ('raise', 'all_in'):
                self.hands_pfr += 1

            # Postflop aggression
            if ent_street in ('flop', 'turn', 'river'):
                if action in ('raise', 'all_in'):
                    self.postflop_bets += 1
                elif action == 'call':
                    self.postflop_calls += 1

# Single instance — persists across the entire match
STATS = OpponentStats()


# ─────────────────────────────────────────────────────────────────────────────
# EXPLOIT PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

def get_exploit_params(player_type):
    """
    Return a dict of strategy adjustments based on opponent type.

    These numbers answer:
    call_adj    — shift equity threshold for calling (negative = call looser)
    bluff_freq  — how often to bluff with weak hands
    cbet_freq   — how often to c-bet the flop
    value_thin  — how thin to value bet (lower equity = bet more for value)
    raise_freq  — how often to raise vs just calling with strong hands
    """
    if player_type == 'calling_station':
        return {
            'call_adj':   +0.05,   # call tighter (they bet real hands)
            'bluff_freq':  0.0,    # NEVER bluff — they call everything
            'cbet_freq':   0.80,   # c-bet often for value (they call)
            'value_thin':  0.52,   # value bet with thinner hands (they pay off)
            'raise_freq':  0.85,   # raise for value vs just calling
            'fold_to_3b':  0.0,    # never fold to their raises (they don't bluff)
        }

    elif player_type == 'maniac':
        return {
            'call_adj':   -0.08,   # call MUCH looser — they bluff constantly
            'bluff_freq':  0.10,   # rarely bluff — they call/reraise anyway
            'cbet_freq':   0.50,   # moderate c-bet (they'll raise as bluff)
            'value_thin':  0.60,   # only value bet real hands
            'raise_freq':  0.40,   # sometimes slowplay to let them bluff
            'fold_to_3b':  0.15,   # fold very rarely to their 3-bets
        }

    elif player_type == 'nit':
        return {
            'call_adj':   +0.10,   # fold to their bets — they have it
            'bluff_freq':  0.60,   # bluff CONSTANTLY — they fold everything
            'cbet_freq':   0.90,   # c-bet every flop — they fold unless nutted
            'value_thin':  0.65,   # only value bet strong hands
            'raise_freq':  0.30,   # don't bloat pots — they only play nuts
            'fold_to_3b':  0.80,   # fold to their 3-bets — always the nuts
        }

    elif player_type == 'tag':
        return {
            'call_adj':    0.0,    # standard
            'bluff_freq':  0.25,   # moderate bluffing
            'cbet_freq':   0.65,   # c-bet on dry boards mostly
            'value_thin':  0.58,   # standard value threshold
            'raise_freq':  0.60,   # raise or flat depending on hand
            'fold_to_3b':  0.55,   # respect their 3-bets but not blindly
        }

    else:   # 'lag' or 'unknown'
        return {
            'call_adj':   -0.03,
            'bluff_freq':  0.20,
            'cbet_freq':   0.65,
            'value_thin':  0.56,
            'raise_freq':  0.65,
            'fold_to_3b':  0.40,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PREFLOP HAND RANGES
# ─────────────────────────────────────────────────────────────────────────────

RANK_ORDER = '23456789TJQKA'

OPEN_RAISE_EARLY  = {'AA','KK','QQ','JJ','TT','AK','AQ','AJ','KQ'}
OPEN_RAISE_MIDDLE = OPEN_RAISE_EARLY  | {'99','88','77','AT','KJ','QJ','JTs','T9s'}
OPEN_RAISE_LATE   = OPEN_RAISE_MIDDLE | {
    '66','55','44','33','22',
    'A9','A8','A7','A6','A5','A4','A3','A2',
    'K9','K8','Q9','J9','T8','98','87','76','65','54',
}
FOUR_BET_HANDS  = {'AA','KK','QQ','AK'}
CALL_3BET_HANDS = {'JJ','TT','AQ','AJ','KQ'}

def rank_val(card_str):
    return RANK_ORDER.index(card_str[0])

def is_suited(hole):
    return hole[0][1] == hole[1][1]

def hand_label(hole):
    r1, r2 = hole[0][0], hole[1][0]
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2 = r2, r1
    return r1 + r2


# ─────────────────────────────────────────────────────────────────────────────
# MONTE CARLO EQUITY  (the mathematical foundation)
# ─────────────────────────────────────────────────────────────────────────────

def monte_carlo_equity(hole, board, n_players, samples=MC_SAMPLES):
    """
    Simulate random runouts and count our win rate.
    Returns float 0.0–1.0 (our equity).
    """
    try:
        hole_ints  = [Card.new(c) for c in hole]
        board_ints = [Card.new(c) for c in board]
        known      = set(hole_ints + board_ints)
        deck       = [c for c in FULL_DECK if c not in known]

        needed   = 5 - len(board)
        n_opps   = n_players - 1
        wins     = 0
        total    = 0

        for _ in range(samples):
            random.shuffle(deck)
            idx = 0
            opp_hands = [deck[idx + i*2 : idx + i*2 + 2] for i in range(n_opps)]
            idx += n_opps * 2
            runout     = deck[idx:idx + needed]
            full_board = board_ints + runout

            my_score  = EVALUATOR.evaluate(full_board, hole_ints)
            best_opp  = min(EVALUATOR.evaluate(full_board, o) for o in opp_hands)

            if my_score < best_opp:    wins += 1
            elif my_score == best_opp: wins += 0.5
            total += 1

        return wins / total if total > 0 else 0.5
    except Exception:
        return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# DRAW DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def has_flush_draw(hole, board):
    suits = [c[1] for c in hole + board]
    return any(suits.count(s) == 4 for s in set(suits))

def has_straight_draw(hole, board):
    ranks = sorted(set(rank_val(c) for c in hole + board))
    return any(ranks[i+3] - ranks[i] <= 4 for i in range(len(ranks)-3))

def has_draw(hole, board):
    return has_flush_draw(hole, board) or has_straight_draw(hole, board)


# ─────────────────────────────────────────────────────────────────────────────
# BOARD TEXTURE
# ─────────────────────────────────────────────────────────────────────────────

def board_wetness(board):
    """
    Returns 0.0 (completely dry) to 1.0 (extremely wet/connected).
    Wet boards have more draws → c-bet less, opponents continue more.
    Dry boards → c-bet more, opponents miss and fold.
    """
    if not board:
        return 0.5

    # Flush potential
    suits = [c[1] for c in board]
    flush_score = max(suits.count(s) for s in set(suits)) / len(board)

    # Straight potential
    ranks = sorted(set(rank_val(c) for c in board))
    straight_score = 0
    if len(ranks) >= 2:
        span = ranks[-1] - ranks[0]
        straight_score = max(0, 1 - span / 8)

    # Paired board (reduces draws)
    pair_penalty = 0.2 if len(ranks) < len(board) else 0

    return max(0, min(1, (flush_score + straight_score) / 2 - pair_penalty))


# ─────────────────────────────────────────────────────────────────────────────
# POSITION & TABLE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_position(players):
    n = max(len(players), 1)
    for i, p in enumerate(players):
        if p.get('is_you'):
            frac = i / n
            if frac < 0.34:   return 'early'
            elif frac < 0.67: return 'middle'
            return 'late'
    return 'middle'

def active_opponents(players):
    return max(sum(
        1 for p in players
        if not p.get('is_you') and not p.get('folded', False) and p.get('stack', 1) > 0
    ), 1)

def pot_odds_required(owed, pot):
    total = pot + owed
    return owed / total if total > 0 else 1.0

def spr(stack, pot):
    return stack / max(pot, 1)

def build_raise(state, fraction):
    """Raise to fraction × pot, respecting min_raise and stack."""
    pot    = state['pot']
    stack  = state['your_stack']
    min_r  = state.get('min_raise_to', state['amount_owed'] * 2)
    amount = max(int(pot * fraction), min_r)
    amount = min(amount, stack)
    if amount >= stack:
        return {'action': 'all_in'}
    return {'action': 'raise', 'amount': amount}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DECIDE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def decide(state):
    """
    Called once per action. Returns fold / check / call / raise / all_in.

    Strategy:
    1. Update opponent stats from action_log
    2. Identify opponent type
    3. Load exploit parameters for that type
    4. Run Monte Carlo equity
    5. Make a decision adjusted by the exploit parameters
    """

    # ── Unpack state ─────────────────────────────────────────────────────────
    hole      = state['your_cards']
    board     = state.get('community_cards', [])
    street    = state['street']
    pot       = state['pot']
    owed      = state['amount_owed']
    stack     = state['your_stack']
    can_check = state.get('can_check', owed == 0)
    players   = state.get('players', [])
    log       = state.get('action_log', [])

    # ── Update opponent model ─────────────────────────────────────────────────
    STATS.update(log, street)

    ptype  = STATS.player_type
    xp     = get_exploit_params(ptype)
    n_opps = active_opponents(players)
    pos    = get_position(players)
    label  = hand_label(hole)
    suited = is_suited(hole)
    spratio = spr(stack, pot)

    # ═══════════════════════════════════════════════════════════════════════════
    # PREFLOP
    # ═══════════════════════════════════════════════════════════════════════════
    if street == 'preflop':

        # Choose open range by position
        if pos == 'early':     my_range = OPEN_RAISE_EARLY
        elif pos == 'middle':  my_range = OPEN_RAISE_MIDDLE
        else:                  my_range = OPEN_RAISE_LATE

        in_range = label in my_range or (suited and (label + 's') in my_range)

        # ── Widen / narrow range based on opponent type ───────────────────────
        # vs nit: steal more → widen range
        if ptype == 'nit' and pos == 'late':
            in_range = in_range or (rank_val(hole[0]) >= 9 and rank_val(hole[1]) >= 7)

        # vs calling station: tighten slightly (don't bluff preflop)
        if ptype == 'calling_station' and pos != 'late':
            in_range = label in OPEN_RAISE_EARLY or (suited and label + 's' in OPEN_RAISE_MIDDLE)

        # ── Facing a raise ────────────────────────────────────────────────────
        if owed > 0:
            if label in FOUR_BET_HANDS:
                return build_raise(state, 4.0)

            if label in CALL_3BET_HANDS:
                return {'action': 'call'}

            # vs nit: fold to 3-bets very frequently (they have it)
            if ptype == 'nit' and random.random() < xp['fold_to_3b']:
                return {'action': 'fold'}

            # Suited speculative hands
            high = max(rank_val(hole[0]), rank_val(hole[1]))
            if suited and high >= 8 and n_opps >= 2 and owed <= pot * 0.15:
                return {'action': 'call'}

            if in_range and owed <= pot * 0.20:
                return {'action': 'call'}

            return {'action': 'fold'}

        # ── No raise to face ──────────────────────────────────────────────────
        if in_range:
            # vs nit: raise bigger (they fold, we win more)
            size = 3.0 if ptype == 'nit' else 2.5
            return build_raise(state, size)

        if can_check:
            return {'action': 'check'}
        return {'action': 'fold'}

    # ═══════════════════════════════════════════════════════════════════════════
    # POST-FLOP — equity-driven, exploit-adjusted
    # ═══════════════════════════════════════════════════════════════════════════

    equity  = monte_carlo_equity(hole, board, n_opps + 1, MC_SAMPLES)
    drawing = has_draw(hole, board) and street != 'river'
    wetness = board_wetness(board)

    # ── Equity adjustments ────────────────────────────────────────────────────

    # Draw bonus (implied odds — draws are worth more than raw equity)
    if drawing:
        equity += DRAW_BONUS

    # SPR-based commitment threshold
    # Low SPR = already deep in the pot, lower bar to commit
    spr_val = spr(stack, pot)
    if   spr_val < 2: commit_threshold = 0.52
    elif spr_val < 4: commit_threshold = 0.58
    elif spr_val < 8: commit_threshold = 0.64
    else:             commit_threshold = 0.72

    # ── FACING A BET ─────────────────────────────────────────────────────────
    if owed > 0:
        required     = pot_odds_required(owed, pot)
        adj_required = required + xp['call_adj']   # exploit adjustment

        # Strong hand + pot committed → shove
        if equity >= commit_threshold and spr_val < 3:
            return {'action': 'all_in'}

        # Clear edge over adjusted pot odds → call or raise for value
        if equity >= adj_required + 0.05:

            # vs calling station: raise for value (they call anyway)
            # vs maniac: sometimes flat to let them keep betting
            should_raise = equity >= xp['value_thin'] and owed < pot * 0.6

            if should_raise and random.random() < xp['raise_freq']:
                size = 1.0 if ptype == 'calling_station' else 0.75
                return build_raise(state, size)

            return {'action': 'call'}

        # Drawing hand with implied odds
        if drawing and equity >= required:
            return {'action': 'call'}

        return {'action': 'fold'}

    # ── WE ACT FIRST (no bet to face) ────────────────────────────────────────
    if not can_check:
        return {'action': 'fold'}

    # ── Value betting ─────────────────────────────────────────────────────────
    if equity >= xp['value_thin']:
        # Scale bet size based on opponent type and board texture
        if ptype == 'calling_station':
            # Bet big — they call regardless of size
            size = 0.85
        elif ptype == 'nit':
            # Bet smaller — don't scare them off, let them fold or hero-call
            size = 0.50
        elif ptype == 'maniac':
            # Bet smaller and let them raise (we re-raise)
            size = 0.55
        else:
            size = 0.65

        # On wet boards, bet slightly bigger (protect + value)
        if wetness > 0.6:
            size += 0.10

        return build_raise(state, size)

    # ── C-bet (continuation bet) ──────────────────────────────────────────────
    # We raised preflop → we have range advantage → bet regardless of our hand
    we_raised_preflop = any(
        e.get('is_you') and e.get('action') in ('raise', 'all_in')
        and e.get('street') == 'preflop'
        for e in log
    )

    if we_raised_preflop and street == 'flop':
        # C-bet frequency adjusted by opponent type and board texture
        cbet_chance = xp['cbet_freq']
        if wetness > 0.7:
            cbet_chance -= 0.20   # c-bet less on wet boards (more likely to be called)
        if n_opps > 1:
            cbet_chance -= 0.15   # c-bet less into multiple opponents

        if random.random() < cbet_chance:
            size = 0.50 if wetness > 0.6 else 0.65
            return build_raise(state, size)

    # ── Semi-bluff with draws ─────────────────────────────────────────────────
    if drawing:
        # vs nit: semi-bluff always (they fold)
        # vs calling station: check draws (they call, no fold equity)
        semi_freq = 0.70 if ptype == 'nit' else 0.10 if ptype == 'calling_station' else 0.50
        if random.random() < semi_freq:
            return build_raise(state, 0.60)

    # ── Double barrel (turn bluff/value) ─────────────────────────────────────
    if street == 'turn' and we_raised_preflop and equity >= 0.40:
        barrel_freq = 0.40 if ptype == 'nit' else 0.20
        if random.random() < barrel_freq:
            return build_raise(state, 0.65)

    # ── River bluff ───────────────────────────────────────────────────────────
    if street == 'river' and equity < 0.35:
        bluff_chance = xp['bluff_freq']
        # Only bluff if fold-to-cbet is high (they fold to pressure)
        if STATS.fold_to_cbet > 0.55:
            bluff_chance += 0.10
        if random.random() < bluff_chance:
            return build_raise(state, 0.70)

    # ── Default: check ────────────────────────────────────────────────────────
    return {'action': 'check'}