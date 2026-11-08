# Labeled change corpus v1

These 32 tiny public synthetic Python changes are data, never executable tests.
The first 20 retain the original curated corpus; 12 additions challenge scope,
exact head lines, multiple findings, data flow, security and reachability.

Labels were manually assigned from each before/after change and its rationale,
before measuring outputs. There are 16 defect labels across 15 flawed cases and
17 clean changes. The matching scope is changed-line correctness, directly
demonstrated security and the existing mutable-default/finally policy. An
unchanged pre-existing defect is deliberately out of scope. Clean does not mean
free of every conceivable vulnerability. Do not execute/import these files or
install their dependencies to determine labels.

Each label means one issue of the exact rule at an exact one-based head line in
`demo.py`. All labels must map to added/replacement lines. Wrong-line predictions
are FP plus FN; extra predictions on positive cases count as FP too. The two
security/data-flow misses and two unreachable-code FPs remain in the corpus.

`baseline.json` is a reviewed regression floor, not a production quality target.
It pins the corpus hash and currently observed 0.875 precision/recall and 2/17
clean-case FP rate. Its values are hand-maintained policy inputs, not generated
measurement artifacts. A corpus/rule change requires independent label review,
a new measurement and an explained baseline change. Never silently relabel a
miss to make a gate pass. Add larger, multi-file, language and representative
real-world holdout sets before drawing general quality conclusions.
