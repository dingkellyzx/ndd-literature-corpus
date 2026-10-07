# Relevance Screening — First Debug Run Review

Run: `bash scripts/run_all.sh` started 2026-10-07 14:02 (+08), screening 14:03–14:38.
Model: `qwen3:14b` via Ollama 0.32.15, temperature 0, prompt version `1`.
Generated report: `data/processed/relevance_debug_report.txt`.
Per the plan's first-evaluation rule, **no prompt, threshold, or signal tuning was applied** after this run.

## Verification

| Check | Result |
| --- | --- |
| `pytest -q` | 83 passed |
| `ruff check src scripts tests` | clean |
| `mypy src/ndd_corpus` | clean |
| `python -m build` | sdist + wheel built |
| Original `articles` / `article_sections` / `article_disease_retrieval` | SHA-256 identical before and after screening |
| One relevance record per article | 100 records, 100 unique `article_id`s, same set as `articles.parquet` |
| `articles_relevant` = eligible set | yes; no `LOW` retained; schema identical to `articles.parquet` |
| Classifier errors | 0 (`errors.jsonl` not created) |
| Cache rerun | 100/100 cache hits, 0.3 s, no Ollama calls |

Row counts:

| File | Rows |
| --- | --- |
| `articles.parquet` | 100 |
| `article_relevance.parquet` | 100 |
| `articles_relevant.parquet` | 76 |
| `article_sections_relevant.parquet` | 0 (upstream `article_sections.parquet` is also 0 — see Known issues) |

## Distribution

| | HIGH | POSSIBLE | LOW | Retained |
| --- | --- | --- | --- | --- |
| All candidates (100) | 63 | 13 | 24 | 76 (76%) |
| Generic query (`broad_ndd`) | 63 | 13 | 24 | |
| Disease queries (`disease`) | 0 | 0 | 0 | |

The debug run's 100-article cap was filled entirely by the first (generic) query, so
there are no disease-query papers to compare yet.

Both no-abstract papers (19552920, 19679353) were classified from title/MeSH and came
out `HIGH`; neither defaulted to `LOW`.

## Target PMIDs

- **PMID 18024065 — LOW, rejected.** Case report of methylphenidate-associated coronary
  vasospasm/MI in adult ADD. Model reason: focus is a medication adverse effect, not NDD
  characterization. Matches the expected outcome. Note the abstract says "toxic side
  effects"; no deterministic negative signal fired.
- **PMID 18690540 — LOW, rejected.** Assertive outreach to close the adolescent substance
  abuse treatment gap. Model reason: focus is treatment access/policy with NDD only as a
  MeSH comorbidity. Negative signals `outreach` and `substance abuse treatment` fired.
  Matches the expected outcome.

## Manual review (all 24 LOW, all 13 POSSIBLE, 20 HIGH)

### LOW (24) — no clear false LOW

18 are clearly correct: acquired/adult conditions (stroke dysgraphia 19449254, visual
neglect 19484647, Alzheimer Aβ mouse 19660564, rat stress 19666130), drug trials and
meta-analyses (19474461, 19568826, 19627427, 19706876), teacher training 19474460,
cultural-practice case 19465731, EFA methods review 19609833, therapy process 19634048,
bipolar/antisocial/psychopathology epidemiology (19686330, 19688258, 19707865), hearing
loss behaviour 19686333, and both target PMIDs.

Borderline (candidate false LOW under a recall-first reading):

- **19494358** — features of children with complex partial epilepsy needing combination
  therapy; developmental disability is one of the discriminating features. Closest to a
  false LOW; `POSSIBLE` would be more recall-consistent.
- **19665851** — ADHD and obesity as "two facets of the same disease" (gene–environment
  hypothesis). ADHD is half the central topic; `POSSIBLE` arguable.
- **19448149** — Conners' CPT construct validity across ADHD and other groups. Defensible
  `LOW`, but inconsistent with 18728238 (same test's factor structure) which got `POSSIBLE`.
- 19381426 (psychiatric prevalence cohort incl. ADHD), 19487578 (ADHD rating factor
  structure), 19644747 (parental resolution in ASD) — defensible `LOW`. 19381426's reason
  wrongly states the paper is "not neurodevelopmental".

### POSSIBLE (13) — used as a "middle relevance" bucket

Genuinely uncertain and appropriately retained: 18728238, 19369016, 19381995, 19400978,
19489749, 19490743, 19521350, 19597797, 19636604.

Treatment/intervention or diagnostic-validity papers that the spec's `LOW` definition
covers, but which came out `POSSIBLE`: 19401504 (methylphenidate response), 19441138
(Ginkgo biloba), 19697119 (computer-based intervention), 19439760 (ADHD simulation).
This errs toward recall, but is inconsistent with the atomoxetine trials labelled `LOW`.

Most `POSSIBLE` reasons say "does not provide genetic/variant evidence" rather than
"insufficient information", so the model uses `POSSIBLE` for NDD-focused but
less-useful papers, not strictly for insufficient metadata.

### HIGH (first 20 by `article_id`, plus scan of the remaining 43)

Clearly HIGH (9/20): 18607376 (AGC1/ASD genetics), 19204064 (TACR1/ADHD), 19362436
(CDKL5 Rett variant), 19362867 (infantile spasms prognosis), 19453835 (polymicrogyria),
19461121 (GAMT deficiency case with mutation), 19502577 (CP long-term outcomes),
19522881 (familial Fahr disease case), 19549204 (congenital perisylvian dysfunction).

Defensible but generous (9/20): cognitive/language/imaging phenotype or epidemiology of
ADHD/ASD/ID — 18974079, 19343567, 19343578, 19347237, 19365085, 19416322, 19520999,
19543791, 19549207.

False HIGH (2/20):

- **19196528** — social and medical care of preschool children with epilepsy; largely
  service utilization, which the spec lists under `LOW`.
- **19250251** — behavioural outcomes after preschool mild traumatic brain injury; an
  acquired injury, with ADHD symptoms only as an outcome.

Additional questionable HIGH outside the sample: 19637100 (acquired autistic traits after
mPFC damage), 19649699 (ABA vs TEACCH treatment models), 19690953 (selective mutism),
19669402 (bullying prevalence in ASD), 19709853 (DCD questionnaire psychometrics — cf.
CPT validity `LOW`).

Evidence types are applied loosely: `natural_history` is attached to cross-sectional
studies (e.g. 19666104 monocyte responses, 19646533 functional connectivity,
19683584 MRI classification). Do not rely on `evidence_types` for downstream filtering
without further review.

## Findings summary

1. **Recall goal met on this sample.** No paper with NDD genetic, phenotype, natural
   history, or onset evidence was rejected. 3 borderline LOWs (19494358, 19665851,
   19448149) would be safer as `POSSIBLE`.
2. **HIGH is generous (63%).** This is a precision issue that does not affect retention,
   since `HIGH` and `POSSIBLE` are both retained. It matters only if downstream code
   prioritizes `HIGH`.
3. **Labels are inconsistent within paper types** (treatment trials: LOW vs POSSIBLE vs
   HIGH; psychometric validation: LOW vs POSSIBLE vs HIGH).

## Defects found during verification

- **Fixed (22cc4f9):** the debug report counted branches `generic_ndd`/`disease_name`,
  but the query builder emits `broad_ndd`/`disease`, so per-branch counts were always zero
  on real data.
- **Fixed in 0640baf — deterministic signals missed plurals.** `_matches` requires an exact word,
  and spec terms are singular, so "mutations", "variants", "seizures", "genes" and
  "adverse effects" do not fire `mutation`/`variant`/`seizure`/`gene`/`adverse effect`.
  `detect_relevance_signals("Novel FOXG1 mutations and variants", "children with seizures
  and adverse effects; genes")` returns no signals. In this run 1–3 papers per term lost
  the signal entirely, and 19627427's "adverse effects" fired no negative signal. The
  final word of each phrase now also matches its regular plural.
- **Upstream, out of scope — PMC sections are never joined.** `pmc/parser.py` reads only
  `article-id[@pub-id-type='pmc']`, but current PMC XML (JATS 1.4) uses `pmcid`, so all
  parsed PMC rows have `pmcid=None`. As a result `merge_corpus` drops all 216 sections and
  `article_sections(_relevant).parquet` are empty. Raised as a separate task.

## Throughput

The first pass took about 35 min for 100 papers (~21 s/paper). Qwen3 thinking is enabled by
default through the OpenAI-compatible endpoint: one probe returned ~1.5k characters of
`reasoning` and took 18 s. The code reads only `content`, so no chain-of-thought is
stored. At this rate, 100k candidates would take about 24 days. Disabling thinking would
probably give a large speed-up, but it changes classifier behaviour and should be
evaluated like any other tuning change.

## Second run — plural signals fixed, thinking disabled

Changes: plural-tolerant signal matching (0640baf) and `relevance.think: false`, which
sends `reasoning_effort: "none"` (5773445). Every request hash changed, so all 100 papers
were reclassified. Baseline labels were kept for comparison.

| | HIGH | POSSIBLE | LOW | Retained | Time | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| First run (thinking on) | 63 | 13 | 24 | 76 | ~35 min (~21 s/paper) | 0 |
| Second run (thinking off) | 48 | 24 | 28 | 72 | 385 s (3.9 s/paper) | 0 |

Baseline (rows) × second run (columns); 73/100 agree:

| | HIGH | POSSIBLE | LOW |
| --- | --- | --- | --- |
| HIGH | 47 | 12 | 4 |
| POSSIBLE | 1 | 7 | 5 |
| LOW | 0 | 5 | 19 |

Deterministic signals changed for 30 papers. Papers with any negative signal went from
1 to 2. Both target PMIDs remain `LOW` and rejected.

### Newly rejected (9)

- Consistent with the spec's `LOW` definition (treatment, intervention, or NDD incidental),
  and fixing the treatment-paper inconsistency noted above: 19401504 (methylphenidate
  response), 19441138 (Ginkgo biloba), 19697119 (computer-based intervention), 19649699
  (ABA vs TEACCH), 19521350 (obesity prevalence across chronic conditions), 19439760
  (simulating ADHD).
- Borderline: 19669402 (bullying among adolescents with ASD); 19590245 (urinary biomarkers
  for neonatal HIE prognosis; HIE is acquired, but the outcome is neurodevelopmental).
- **False LOW: 19652018** (tip-of-the-tongue and word-retrieval deficits in dyslexia), an
  NDD phenotype paper. It is also unstable: three repeat classifications with thinking off
  all returned `POSSIBLE`. The cached `LOW` stays until its request hash changes.

### Newly retained (5)

19665851 (ADHD and obesity; one of the borderline LOWs flagged above) and 19381426
(psychiatric prevalence cohort incl. ADHD) are improvements. 19465731 (cultural-practice
case), 19686330 (bipolar-spectrum epidemiology), and 19686333 (hearing-loss language and
behaviour) are over-retention. This is harmless for recall.

The 12 HIGH → POSSIBLE moves are mostly the "defensible but generous" cognitive-phenotype
papers, plus two flagged false HIGH (19637100 acquired mPFC damage, 19690953 selective
mutism). All stay retained. `POSSIBLE` reasons now more often cite insufficient abstract
detail, which is closer to the spec's meaning. 19494358 and 19448149 remain borderline `LOW`.

### Attribution and reproducibility

The 14 papers whose retention changed were re-classified without touching the cache:

- Only 2 of the 14 had changed signals: 19401504 and 19441138.
- With thinking re-enabled on the other 12 (identical payload to the baseline), 4 of 10
  checked papers still returned a different label than the baseline run (19439760,
  19521350, 19665851, 19697119). **Thinking mode is not reproducible at temperature 0.**
- With thinking off, 13/14 papers returned the cached label on all three repeats. The
  exception is 19652018 (cached `LOW`, repeats `POSSIBLE`).

Conclusion: disabling thinking is about 5.5× faster and much more reproducible. It is
stricter on treatment and intervention papers, matching the spec, and less generous with
`HIGH`. Retention fell by 4 net, with one confirmed false LOW (19652018) and two
borderline.

## Remaining recommendations

1. Optionally tighten the prompt: NDD cognitive and phenotype studies (e.g. dyslexia,
   ASD language) are at least `POSSIBLE`; acquired brain injury is not an NDD; `POSSIBLE`
   means insufficient metadata. Re-check 19652018, 19590245, 19669402, 19494358.
2. Re-run screening on a debug window that includes disease-query papers.
