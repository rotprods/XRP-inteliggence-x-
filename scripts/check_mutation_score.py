from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def _integer(root: ET.Element, key: str) -> int:
    return sum(int(node.attrib.get(key, "0")) for node in root.findall(".//testsuite"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce mutation-test quality from mutmut JUnit XML")
    parser.add_argument("junit_xml", type=Path, nargs="?", default=Path("quality/mutmut.xml"))
    parser.add_argument("--threshold", type=float, default=90.0)
    parser.add_argument("--report", type=Path, default=Path("quality/mutation_policy.json"))
    args = parser.parse_args()

    root = ET.parse(args.junit_xml).getroot()
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = root.findall(".//testsuite")
    if not suites:
        raise SystemExit("mutmut JUnit XML contains no testsuite")

    total = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    if total <= 0:
        raise SystemExit("mutmut JUnit XML contains zero mutants")

    killed = total - failures - errors - skipped
    score = 100.0 * killed / total
    status = "PASS" if score >= args.threshold and errors == 0 and skipped == 0 else "FAIL"
    report = {
        "status": status,
        "mutation_score": round(score, 4),
        "threshold": args.threshold,
        "mutants": total,
        "killed": killed,
        "survived_or_policy_failure": failures,
        "errors": errors,
        "skipped": skipped,
        "policy": "suspicious and untested mutants must be emitted as failures",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
