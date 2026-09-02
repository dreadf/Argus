# Archive

Superseded planning docs, kept for history rather than deleted — this project's own honesty
about what it tried and abandoned is part of its story, and `git log --follow` still shows each
file's original commits from its root-level path.

- **`ML_Experiment_Plan.md`** — the original equity-direction research plan. Superseded by
  `VOLATILITY_ML_PLAN.md`; the 5-day direction question it posed is closed with a documented
  negative answer in `EXPERIMENT.md`, Experiments 0-10.
- **`TRADING_SYSTEM_PLAN.md`** — design doc for a market-neutral long/short equity system meant
  to sit downstream of the direction model above. Marked "design only, no code written" at the
  time; its equity long/short parts are superseded by `OPTIONS_SYSTEM_PLAN.md`, which reused its
  Layer 0/1 ideas.
- **`Project_Context_and_Plan_Updated.md`** — broader project narrative and the pivot from
  absolute to cross-sectional direction prediction. Its gating criteria and risk tables were
  translated into `OPTIONS_SYSTEM_PLAN.md`'s current design; the direction it describes was
  itself later abandoned for the options-selling pivot.
- **`RESEARCH_pooling_vs_individual.md`** — literature review comparing pooled vs. per-stock vs.
  ensemble model architectures, written to decide how to scale the equity feature-ablation
  pipeline. Fully absorbed as a citation inside `EXPERIMENT.md`.

Current, actively-maintained docs remain at the repo root: `README.md`, `EXPERIMENT.md`,
`SOURCES.md`, `PROGRESS.md`, `OPTIONS_SYSTEM_PLAN.md`, `VOLATILITY_ML_PLAN.md`.
