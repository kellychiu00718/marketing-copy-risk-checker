"""3개 모드(rules / llm / cascade)를 같은 모의 케이스로 비교한다. 프로토콜: docs/eval_protocol.md

사용:
  .venv/bin/python tests/run_eval.py dev  [모드...] [--repeat N]
  .venv/bin/python tests/run_eval.py test [모드...] [--repeat N]   # 블라인드: 규칙 수정 후 최종 1회만
결과: 모드별 혼동행렬, 정밀도/재현율(Wilson 95% CI), AI 호출 수·토큰, 반복 간 판정 일치율, 쌍별 McNemar(exact).
"""
import hashlib
import sys
from datetime import date
from itertools import combinations
from math import comb, sqrt
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from preflight.pipeline import review  # noqa: E402

args = sys.argv[1:]
split = args.pop(0) if args and args[0] in ("dev", "test") else "dev"
repeat = 1
if "--repeat" in args:
    i = args.index("--repeat")
    repeat = int(args[i + 1])
    del args[i:i + 2]
MODES = args or ["rules", "llm", "cascade"]
path = ROOT / "tests" / f"cases_{split}.yaml"
cases = yaml.safe_load(open(path, encoding="utf-8"))
print(f"[{split}] {len(cases)}건 · sha256 {hashlib.sha256(path.read_bytes()).hexdigest()[:16]}… · 반복 {repeat}회")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def fmt(k: int, n: int) -> str:
    if n == 0:
        return "  n/a (0/0)"
    lo, hi = wilson(k, n)
    return f"{k / n:.2f} [{lo:.2f}-{hi:.2f}]"


preds: dict[str, list[list[bool]]] = {m: [] for m in MODES}  # mode → run → case
stats = {}
for m in MODES:
    tp = fp = fn = tn = calls = tin = tout = 0
    for run in range(repeat):
        out = []
        for c in cases:
            r = review(c["text"], date.fromisoformat(c["launch"]), m)
            pred, gold = r["needs_human_review"], c["expect_review"]
            out.append(pred)
            if run == 0:
                tp += pred and gold
                fp += pred and not gold
                fn += (not pred) and gold
                tn += (not pred) and (not gold)
                calls += r["llm_called"]
                tin += r["usage"]["input_tokens"]
                tout += r["usage"]["output_tokens"]
                if pred != gold:
                    pol = " (policy)" if c.get("policy") else ""
                    err = f" ERR={r['error']}" if r["error"] else ""
                    print(f"  [{m}] 오답 {c['id']} [{c['tag']}]{pol} 정답={gold} 예측={pred} level={r['level']}{err}")
        preds[m].append(out)
    stats[m] = (tp, fp, fn, tn, calls, tin, tout)

print(f"\n{'mode':8} TP FP FN TN  정밀도 [95%CI]        재현율 [95%CI]        정확도   AI호출  in/out tok")
for m, (tp, fp, fn, tn, calls, tin, tout) in stats.items():
    acc = (tp + tn) / len(cases)
    print(f"{m:8} {tp:2} {fp:2} {fn:2} {tn:2}  {fmt(tp, tp + fp):20} {fmt(tp, tp + fn):20} {acc:.2f}   {calls:4}   {tin}/{tout}")

if repeat > 1:
    print("\n반복 간 판정 일치율(같은 입력, 같은 모드):")
    for m in MODES:
        runs = preds[m]
        same = sum(len({runs[r][i] for r in range(repeat)}) == 1 for i in range(len(cases)))
        print(f"  {m:8} {same}/{len(cases)} ({same / len(cases):.0%})")

gold_all = [c["expect_review"] for c in cases]
corr = {m: [p == g for p, g in zip(preds[m][0], gold_all)] for m in MODES}
for a, b in combinations(MODES, 2):
    oa = sum(x and not y for x, y in zip(corr[a], corr[b]))
    ob = sum(y and not x for x, y in zip(corr[a], corr[b]))
    print(f"McNemar {a} vs {b}: {a}만 정답 {oa}, {b}만 정답 {ob}, p={mcnemar_exact(oa, ob):.3f}")
