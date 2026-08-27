const methodLabels = {
  en: {
    descriptive_summary: "Descriptive analysis",
    welch_t_test: "Welch two-group comparison",
    mann_whitney_u: "Mann–Whitney U comparison",
    paired_t_test: "Paired comparison",
    wilcoxon_signed_rank: "Wilcoxon signed-rank comparison",
    welch_anova: "Welch ANOVA",
    kruskal_wallis: "Kruskal–Wallis comparison",
    chi_square_or_fisher: "Chi-square or Fisher exact test",
    pearson_or_spearman: "Pearson or Spearman correlation",
    spearman_rank: "Spearman correlation",
    linear_regression: "Linear regression",
    logistic_regression: "Logistic regression",
  },
  tr: {
    descriptive_summary: "Betimsel analiz",
    welch_t_test: "Welch iki grup karşılaştırması",
    mann_whitney_u: "Mann–Whitney U karşılaştırması",
    paired_t_test: "Eşleştirilmiş karşılaştırma",
    wilcoxon_signed_rank: "Wilcoxon işaretli sıralar karşılaştırması",
    welch_anova: "Welch ANOVA",
    kruskal_wallis: "Kruskal–Wallis karşılaştırması",
    chi_square_or_fisher: "Ki-kare veya Fisher kesin testi",
    pearson_or_spearman: "Pearson veya Spearman korelasyonu",
    spearman_rank: "Spearman korelasyonu",
    linear_regression: "Doğrusal regresyon",
    logistic_regression: "Lojistik regresyon",
  },
} as const;

export function methodLabel(method: string, language: "en" | "tr"): string {
  return methodLabels[language][method as keyof (typeof methodLabels)[typeof language]]
    ?? method.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}
