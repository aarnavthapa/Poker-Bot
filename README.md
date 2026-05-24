# Poker Bot 

A research-driven Texas Hold'em Poker project built on top of the FullHouse's competition framework.

This repository focuses on improving intelligent poker agents through self-play, statistical modelling, Monte Carlo simulations, and learning-based approaches.

---

## Project Overview

The FullHouse engine provides the underlying poker infrastructure:
(I have changed the engine to use treys instead of eval7 for card evaluation)
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

Simple agents used for benchmarking and experimentation:(Completed)

- TemplateBot
- SharkBot
- AggressorBot
- MathematicianBot
- MonteCarloBot

---

### Experimental Bots

Advanced strategy exploration:(Pending Completion)

- CFRBot - (Counterfactual Regret Minimization)
- MCCFRBot - (Monte-Carlo Counterfactual Regret Minimization)
- OpponentModelBot 
- ReinforcementLearningBot

---

### Final Competitive Agent

FinalBot combines:(Pending Completion)

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
├── base_template_bot/
├── practice_bots/
├── experimental/
└── final/

engine/
sandbox/
tests/

requirements.txt
README.md
```


## Running Bots

Install dependencies:

```bash
pip install -r requirements.txt
```

Run a sample bot:

```bash
python bots/practice/random_bot.py
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


---

## Future Improvements

- neural policy networks
- transformer-based decision systems
- real-time adaptation
- distributed self-play training

---

## License

Framework components remain subject to their original license.

Original framework authors retain ownership of framework code.

Bot implementations and additions in this repository are authored independently.