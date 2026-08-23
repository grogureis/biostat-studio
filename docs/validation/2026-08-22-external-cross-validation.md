# External cross-validation — Dunn/Holm post-hoc and power module

Date: 2026-08-22 · Environment: isolated scratch venv (Python 3.12), independent
libraries `scikit-posthocs 0.14.0` and `pingouin 0.6.1`. R was not available on
this machine; scikit-posthocs implements Dunn independently of BioStat Studio's
hand-rolled formula, and pingouin implements its own power solvers independently
of statsmodels.

The pinned expectations below are the exact values asserted by
`services/analysis/tests/test_analyses_reference.py` and
`services/analysis/tests/test_power.py`.

## Dunn pairwise z with Holm adjustment (Kruskal–Wallis reference dataset)

Dataset: C=[7.1, 8.4, 9.2, 6.8, 7.7], B=[5.9, 6.3, 7.0, 6.1], A=[4.2, 5.1, 4.8, 5.5, 4.9].

| Quantity | BioStat Studio | scikit-posthocs | Match |
|---|---|---|---|
| raw p (C–B) | 0.1489611244738834 | 0.1489611244738834 | exact |
| raw p (C–A) | 0.0008807431907417271 | 0.0008807431907417271 | exact |
| raw p (B–A) | 0.09052124460534798 | 0.09052124460534798 | exact |
| Holm p (C–B) | 0.18104248921069596 | 0.18104248921069596 | exact |
| Holm p (C–A) | 0.0026422295722251813 | 0.0026422295722251816 | ≤1 ulp |
| Holm p (B–A) | 0.18104248921069596 | 0.18104248921069596 | exact |

Omnibus H = 11.082857142857144, p = 0.003920921519003687 confirmed via
`scipy.stats.kruskal` (identical to R `kruskal.test` definition with tie
correction).

## Power module vs pingouin / closed forms

| Case | BioStat Studio (statsmodels) | Independent | Δ | Verdict |
|---|---|---|---|---|
| two-sample t, d=0.5 → n/group | 63.765611775409695 | 63.76561019095234 (pingouin) | 2·10⁻⁸ | match |
| two-sample t, n=64 → power | 0.8014595500498423 | 0.8014595579222545 (pingouin) | 8·10⁻⁹ | match |
| paired t, dz=0.5 → n pairs | 33.36713142751997 | 33.367128953330905 (pingouin) | 7·10⁻⁸ | match |
| one-way ANOVA, f=0.25, k=3 → n/group | 52.39646 | 52.39660 (pingouin, η²=f²/(1+f²)) | 3·10⁻⁶ | match |
| two proportions, 0.6 vs 0.4 → n/group | 96.79193707310118 | 96.79217363467849 (closed form 2·((z_{α/2}+z_β)/h)²) | 2.4·10⁻⁶ | match (solver tolerance; rounded n identical: 97, agrees with G*Power) |
| correlation, r=0.5 → n | 29.012300401053597 (→30) | 28.248 (pingouin) | — | **methodological variant, documented** |

The correlation difference is not numerical: pingouin uses a bias-corrected
Fisher transform (`z_r = atanh(r) + r/(2(n−1))`) with a t-based critical value,
while BioStat Studio uses the plain Fisher-z closed form
`n = ((z_{α/2}+z_β)/atanh(r))² + 3` — the convention used by Cohen (1988) and
G*Power's z-approximation, matching the canonical benchmark (n = 29–30 at
r=0.5, α=0.05, power=0.80). BioStat Studio's convention is the slightly more
conservative of the two (larger n) and is named in the API response
(`closed_form_fisher_z`).

Canonical external anchors reproduced exactly by the module: n=64/group for
d=0.5 (Cohen), n=97/group for p₁=0.6 vs p₂=0.4 (G*Power), n=30 for r=0.5
(Hulley sample-size tables).

## Two-proportion convention: arcsine vs pooled z (added after supervisor review)

The two-proportion module uses Cohen's arcsine transform (h). The canonical
n=97 anchor sits at a symmetric point where the arcsine and classical pooled-z
constructions agree, so it does not discriminate between them. Measured per-group
n (α=0.05, power=0.80, two-sided):

| p₁ vs p₂ | arcsine (production) | pooled z | Δ |
|---|---|---|---|
| 0.40 vs 0.60 | 96.79 | 96.92 | −0.1% |
| 0.05 vs 0.20 | 69.20 | 75.12 | −7.9% |
| 0.02 vs 0.10 | 121.32 | 137.15 | −11.5% |

For rare outcomes the arcsine convention systematically yields the smaller n.
Both are legitimate published conventions; the applied one is now named
explicitly in the API response (`method:
statsmodels_normal_solver_arcsine_transform:cohen_h`) and pinned by a
regression test at the asymmetric 0.05 vs 0.20 point. Planners of rare-outcome
studies should be aware that a pooled-z design would require more subjects.

## Known validation boundary

The Dunn z→p tail probability uses `scipy.stats.norm.sf` in both production and
the independent reference (scikit-posthocs also depends on scipy), so the normal
tail function itself is shared rather than independently validated. The Dunn
statistic formula, tie correction, and Holm adjustment are independently
confirmed; validating the tail function would require a non-scipy stack (e.g. R),
which was not available on this machine.

## Conclusion

All Dunn/Holm quantities match an independent implementation to ≤1 ulp; all
power quantities match independent implementations or closed forms within
solver tolerance, except correlation power, where the difference is a
documented convention choice, anchored to the canonical published value.
