#!/usr/bin/env python3
"""Cikarim motorlarini ayni metinler uzerinde karsilastirir.

Kullanim (depo kokunden):
    PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python \
        scripts/eval/run_eval.py --fetch              # korpusu indir
    PYTHONPATH=services/analysis services/analysis/.venv-py312/bin/python \
        scripts/eval/run_eval.py qwen2.5:14b qwen2.5:7b

Korpus metinleri depoya KONULMAZ (PMC yeniden dagitim lisansi belirsiz);
--fetch onlari scripts/eval/corpus/ altina indirir, orasi gitignore'ludur.

NOT: `npm run test:python` bu worktree'de bozuk (venv editable kablolamasi).
Yukaridaki PYTHONPATH bicimi calisir.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "corpus"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DESIGNS = ("cross_sectional", "cohort", "case_control", "trial", "repeated")

# Modele giden istem. Sinif tanimlari kasitli olarak acik yazildi cunku
# olculdu: model tanimsiz birakilinca "cohort + longitudinal follow-up"u
# `repeated` sayma egiliminde - kural motorunun MF1 hatasiyla ayni tuzak.
PROMPT = """You classify the study design of a biomedical methods section.

Answer with EXACTLY ONE of these five values, and nothing else:
cross_sectional | cohort | case_control | trial | repeated

Rules:
- "trial" means the investigators assigned the intervention (randomised or not).
- "cohort" means participants were followed over time without assigned intervention.
  A cohort with longitudinal follow-up is still "cohort", NOT "repeated".
- "repeated" means the SAME subjects were measured at multiple timepoints and the
  analysis compares those timepoints within subject.
- "case_control" means participants were selected by outcome status, then exposure
  was looked at backwards.
- "cross_sectional" means measured at a single point in time, no follow-up.
- If none fits, answer: none

METHODS SECTION:
---
{text}
---

Answer with one word only."""


def fetch_corpus(gold: dict) -> None:
    CORPUS.mkdir(exist_ok=True)
    ids = [i["pmc"] for i in gold["en"] + gold["tr"] + gold["tr_puanlanmayan"]]
    for pmc in ids:
        target = CORPUS / f"{pmc}.txt"
        if target.exists():
            continue
        url = f"{EUTILS}/efetch.fcgi?db=pmc&id={pmc}&retmode=xml"
        with urllib.request.urlopen(url, timeout=60) as response:
            xml = response.read().decode("utf-8", "replace")
        best = ""
        for section in re.findall(r"<sec[^>]*>(.*?)</sec>", xml, re.S):
            title = re.search(r"<title[^>]*>(.*?)</title>", section, re.S)
            if not title:
                continue
            label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", title.group(1))).strip()
            if re.search(r"method|material|gere[çc] ve y[öo]ntem|y[öo]ntem", label, re.I):
                body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", section)).strip()
                if len(body) > len(best):
                    best = body
        if best:
            target.write_text(best)
            print(f"  indirildi {pmc}  {len(best)} karakter")
        else:
            print(f"  ATLANDI   {pmc}  methods bolumu bulunamadi")
        time.sleep(0.4)


def ask_ollama(model: str, text: str, budget: int, timeout: int = 180):
    payload = json.dumps({
        "model": model,
        "prompt": PROMPT.format(text=text[:budget]),
        "stream": False,
        "options": {"temperature": 0, "seed": 1, "num_predict": 12},
    }).encode()
    request = urllib.request.Request(
        "http://localhost:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read())["response"]
    except Exception as exc:  # noqa: BLE001
        return f"HATA:{type(exc).__name__}", time.monotonic() - started
    elapsed = time.monotonic() - started
    lowered = raw.strip().lower()
    for design in DESIGNS:
        if re.search(rf"\b{design}\b", lowered):
            return design, elapsed
    return (None if "none" in lowered else f"?{lowered[:20]}"), elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="*", help="ollama model adlari")
    parser.add_argument("--fetch", action="store_true", help="korpusu indir ve cik")
    args = parser.parse_args()

    gold = json.loads((HERE / "gold_set.json").read_text())
    if args.fetch:
        fetch_corpus(gold)
        return

    from biostat_service.extractors.rule import RuleExtractor, SELECTION_BUDGET
    from biostat_service.methodology_intake import MethodologyDocument

    def rule_design(text: str):
        document = MethodologyDocument("0" * 64, "txt", text, len(text), False, ())
        proposal = RuleExtractor().extract_brief(document).design
        return proposal.value if proposal else None

    for language in ("en", "tr"):
        items = gold[language]
        print(f"\n{'='*70}\n{language.upper()}  (n={len(items)})\n{'='*70}")
        head = f"{'PMC':<11}{'ALTIN':<16}{'KURAL':<16}" + "".join(f"{m:<19}" for m in args.models)
        print(head + "\n" + "-" * len(head))
        tally = {m: 0 for m in args.models}
        rule_ok = 0
        for item in items:
            path = CORPUS / f"{item['pmc']}.txt"
            if not path.exists():
                print(f"{item['pmc']:<11}korpus yok - once --fetch calistirin")
                continue
            text = path.read_text()
            rule = rule_design(text)
            rule_ok += rule == item["gold"]
            cells = []
            for model in args.models:
                answer, secs = ask_ollama(model, text, SELECTION_BUDGET)
                tally[model] += answer == item["gold"]
                cells.append(f"{'+' if answer == item['gold'] else '-'}{answer} ({secs:.1f}s)")
            print(f"{item['pmc']:<11}{item['gold']:<16}"
                  f"{('+' if rule == item['gold'] else '-') + str(rule):<16}"
                  + "".join(f"{c:<19}" for c in cells))
        print("-" * len(head))
        print(f"{'KURAL':<27}{rule_ok}/{len(items)}")
        for model in args.models:
            print(f"{model:<27}{tally[model]}/{len(items)}")


if __name__ == "__main__":
    main()
