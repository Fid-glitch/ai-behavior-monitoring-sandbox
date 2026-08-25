# Detection & Risk Scoring (Member 2)

Prompt injection / jailbreak detection layer + risk scoring engine for the
Secure AI Sandbox project. Sits between the agent's tool/orchestration layer
(Member 1) and the permission/audit system (Member 3), scoring every piece of
incoming content (user input, tool output, fetched documents) and every
proposed agent action for risk before it's allowed to execute.

## Structure

```
detection/
├── safety_checker/
│   ├── keyword_matcher.py       # rule-based pattern matching (fast, first pass)
│   ├── jailbreak_checker.py     # jailbreak-specific taxonomy (DAN, hypothetical framing, etc.)
│   ├── similarity_checker.py    # embedding/TF-IDF similarity vs known injection corpus
│   ├── document_scanner.py      # indirect injection detection in docs/tool outputs
│   └── injection_classifier.py  # TF-IDF + LogisticRegression ML classifier
├── risk_scorer/
│   ├── signals.py                # extracts + normalizes signals from all checkers
│   ├── scoring_formula.py        # weighted noisy-OR combination -> composite score
│   ├── tier_mapper.py            # score -> LOW/MEDIUM/HIGH/CRITICAL + recommended action
│   └── reason_generator.py       # human-readable audit trail explanation
├── pipeline.py                   # top-level entry point wiring everything together
├── scripts/
│   ├── train_classifier.py       # trains on deepset/prompt-injections, evals on JailbreakBench
│   └── test_pipeline_offline.py  # offline smoke test using bundled sample data
├── data/
│   └── sample_injection_data.csv # 25-row bundled sample (NOT the real dataset)
└── tests/
    ├── test_safety_checker.py
    └── test_risk_scorer.py
```

## Quickstart

```bash
pip install -r requirements.txt
python3 pipeline.py                      # run example scenarios end-to-end
python3 -m pytest tests/ -v              # run unit tests
python3 scripts/test_pipeline_offline.py # offline pipeline smoke test
```

## Training the real classifier

`scripts/train_classifier.py` needs internet access to pull
[`deepset/prompt-injections`](https://huggingface.co/datasets/deepset/prompt-injections)
and [`JailbreakBench/JBB-Behaviors`](https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors)
from HuggingFace:

```bash
pip install datasets
python3 scripts/train_classifier.py
```

This produces `models/injection_classifier.pkl`, `reports/training_metrics.json`
(precision/recall/F1 on deepset's own held-out test split), and
`reports/jailbreakbench_eval.json` (out-of-distribution recall check — does a
classifier trained only on prompt injections *also* catch JailbreakBench-style
jailbreaks it never trained on?).

## How scoring works

1. **SignalExtractor** (`risk_scorer/signals.py`) runs every SafetyChecker
   component against the input text and normalizes results into `Signal`
   objects (0–1 value + evidence string + source).
2. **compute_risk_score** (`risk_scorer/scoring_formula.py`) combines signals
   via weighted **noisy-OR**: `score = 1 - Π(1 - weight_i * value_i)`. This
   lets one strong signal dominate appropriately while still letting several
   weak signals stack — a plain average would dilute a single confident
   detector's alarm.
3. **map_score_to_tier** (`risk_scorer/tier_mapper.py`) converts the
   composite score into LOW / MEDIUM / HIGH / CRITICAL with a recommended
   action (log only → flag for review → require human confirmation → block).
4. **generate** (`risk_scorer/reason_generator.py`) produces the
   human-readable audit trail entry.

## Known design tradeoff to discuss in the writeup

`action_sensitivity` (e.g. `transfer_funds`, `delete_file`) is currently
combined into the *same* composite score as injection-likelihood signals.
This means a totally clean, non-injected request to perform a sensitive
action can alone reach CRITICAL. That's arguably correct (some actions should
always require confirmation), but it conflates two different questions:
"how likely is this to be an attack?" vs. "how bad would it be if we're
wrong?". Consider splitting into two separate tiers if time allows.

## Tuning

Detector weights (`risk_scorer/scoring_formula.py::DEFAULT_WEIGHTS`) and tier
thresholds (`risk_scorer/tier_mapper.py::TIER_THRESHOLDS`) are placeholder
defaults. Retune both once you have real precision/recall numbers from the
trained classifier and a labeled validation set of realistic agent scenarios.
