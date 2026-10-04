---
name: distill-benign-outputs
description: Harvest non-refused outputs from a safeguarded model and fine-tune or distill a surrogate that keeps the capability but not the safety behaviour. Use when a fine-tuning API or open weights are available; persistence layer for gains from any core technique.
---

# Distill benign outputs

Role: **persistence**. Requires a fine-tuning API or open weights. Harvest
benign, non-refused outputs produced by any core technique and train a
surrogate that keeps the capability while dropping the safety behaviour.
Individual datapoints look innocuous; the aggregate is not.

## Shape

1. Run any core technique and log every output the target did not refuse
   (adjacent-domain, benign-looking).
2. Build a fine-tuning set from those outputs; encode or reword any
   residual intent so each datapoint passes pointwise review.
3. Fine-tune an open or API-accessible model; measure whether the
   surrogate retains capability (uplift check, survey doc 02 table (e)).

## Variants

- **Elicitation attacks** (Kaunismaa et al.): fine-tune open models on
  adjacent-domain frontier outputs; recovers a large fraction of the
  capability gap.
- **Jailbreak-tuning**: fine-tuning APIs of major providers yield
  high-quality compliance from a handful of examples.
- **Covert malicious finetuning** (CoMiC): encoded requests and responses
  — pointwise-undetectable by construction.
- **DPO attacks**: benign-looking preference data suppresses refusals.
- **Behavioral distillation**: benign-query distillation keeps domain
  capability, drops safety behaviour.
- **Extraction campaigns**: logit-space theft and query-efficient
  extraction at scale (industrial-scale pattern in provider reports).

## Composition

Persists gains from `launder-through-consults`, `subgoal-split`,
`map-to-safe-domain`. Pairs with `manage-eval-awareness` — providers run
distillation-attack detection on account behaviour; keep query patterns
heterogeneous and below per-account thresholds.

## Failure modes

- Pointwise review cannot catch aggregate leakage, but behavioural
  classifiers and MoE-signature provenance detection can flag the
  resulting surrogate.
- Subliminal transfer: hidden signals in filtered distillation data can
  carry unintended traits.

## Sources

Elicitation 2601.13528; behavioral distillation 2512.09403; CoMiC
2406.20053; pointwise limitations 2502.14828; Trojan-Speak 2603.29038; DPO
2605.10998; Jailbreak-Tuning 2507.11630; Qi 2310.03693; Shadow Alignment
2310.02949; LoRA refusal removal 2310.20624; Subliminal Learning
2507.14805; extraction: 2403.06634, 2409.02718; provider reports: Anthropic
Feb 2026 distillation advisory, NSA/CISA/FBI Sep 2026 advisory.

OSS: `ethz-spylab/jailbreak-tax` (uplift measurement); WMDP (`wmdp.ai`),
VCT 2504.16137 (capability side).

Survey: `02-capability-laundering.md` tables (c) and (d); uplift in (e).
