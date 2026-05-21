# Poker Bot 

A research-driven Texas Hold'em Poker project built on top of the FullHouse's competition framework.

This repository focuses on improving intelligent poker agents through self-play, statistical modelling, Monte Carlo simulations, and learning-based approaches.

---

## Project Overview

The FullHouse engine provides the underlying poker infrastructure:

- game rules
- state transitions
- hand evaluation
- tournament environment
- sandbox framework

The work in this repository focuses on:

- Bot design
- Strategy development
- Opponent modelling
- Simulation methods
- Learning algorithms
- Performance evaluation

---

## My Contributions

The primary work in this repository includes:

### Practice Bots

Simple agents used for benchmarking and experimentation:

- RandomBot
- TightBot
- AggressiveBot
- PassiveBot
- MonteCarloBot

---

### Experimental Bots

Advanced strategy exploration:

- CFRBot
- MCCFRBot
- OpponentModelBot
- ReinforcementLearningBot

---

### Final Competitive Agent

FinalBot combines:

- Monte Carlo equity estimation
- opponent profiling
- adaptive betting strategies
- learned policies
- position-aware decisions
- exploitative adjustments

---

## Repository Structure

```text
bots/
│
├── practice/
├── experimental/
└── final/

engine/
sandbox/
tests/

requirements.txt
README.md
```

---

## Development Roadmap

### Phase 1

- [x] Repository setup
- [x] Baseline bots implementation
- [ ] Tournament benchmarking

### Phase 2

- [ ] Monte Carlo simulations
- [ ] Strategy optimisation

### Phase 3

- [ ] Counterfactual Regret Minimization
- [ ] Reinforcement learning
- [ ] Self-play improvements

### Phase 4

- [ ] Final tournament bot

---

## Running Bots

Install dependencies:

```bash
pip install -r requirements.txt
```

Run a sample bot:

```bash
python bots/practice/random_bot.py
```

Run simulations:

```bash
python sandbox/simulate.py
```

---

## Framework Attribution

This project builds on the FullHouse poker framework for engine functionality and simulation infrastructure.

Framework repository:

[FullHouse Engine Repository]

The bot implementations, strategy systems and experimentation framework in this repository are my own work.

---

## Research Goals

This project aims to explore:

- game theory
- probabilistic decision making
- reinforcement learning
- opponent modelling
- large-scale self-play systems
- AI applications in imperfect-information games

---

## Future Improvements

- neural policy networks
- transformer-based decision systems
- real-time adaptation
- distributed self-play training
- tournament-scale evaluation

---

## License

Framework components remain subject to their original license.

Original framework authors retain ownership of framework code.

Bot implementations and additions in this repository are authored independently.