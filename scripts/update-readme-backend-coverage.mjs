import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(process.cwd(), "..");
const coveragePath = path.join(process.cwd(), "coverage", "coverage.json");
const readmePath = path.join(repoRoot, "README.md");

const report = JSON.parse(fs.readFileSync(coveragePath, "utf8"));
const totals = report.totals;

const lines = Number(totals.percent_covered).toFixed(2);
const statements = totals.num_statements
  ? ((Number(totals.covered_lines) / Number(totals.num_statements)) * 100).toFixed(2)
  : lines;
const branches = totals.num_branches
  ? ((Number(totals.covered_branches) / Number(totals.num_branches)) * 100).toFixed(2)
  : "N/A";
const functions = "N/A";

function pickColor(value) {
  const num = Number(value);
  if (num >= 95) return "brightgreen";
  if (num >= 90) return "green";
  if (num >= 80) return "yellow";
  if (num >= 70) return "orange";
  return "red";
}

const badge = `![Backend Coverage](https://img.shields.io/badge/backend%20coverage-${lines}%25-${pickColor(lines)})`;
const section = [
  "## Backend Test Coverage",
  "",
  `${badge}`,
  "",
  "| Metric | Coverage |",
  "| --- | ---: |",
  `| Lines | ${lines}% |`,
  `| Statements | ${statements}% |`,
  `| Branches | ${branches === "N/A" ? "N/A" : `${branches}%`} |`,
  `| Functions | ${functions} |`,
  "",
  "_This section reports backend pytest-cov coverage and is updated automatically by GitHub Actions._",
].join("\n");

const start = "<!-- backend-coverage:start -->";
const end = "<!-- backend-coverage:end -->";
const readme = fs.readFileSync(readmePath, "utf8");

if (!readme.includes(start) || !readme.includes(end)) {
  throw new Error("README backend coverage markers are missing.");
}

const next = readme.replace(
  new RegExp(`${start}[\\s\\S]*?${end}`),
  `${start}\n${section}\n${end}`
);

fs.writeFileSync(readmePath, next);
