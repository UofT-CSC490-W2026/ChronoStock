import fs from "node:fs";
import path from "node:path";

const repoRoot = path.resolve(process.cwd(), "..");
const coverageDir = path.join(process.cwd(), "coverage");
const summaryPath = path.join(coverageDir, "coverage-summary.json");
const finalPath = path.join(coverageDir, "coverage-final.json");
const readmePath = path.join(repoRoot, "README.md");

function percentage(covered, total) {
  if (total === 0) return "100.00";
  return ((covered / total) * 100).toFixed(2);
}

function buildSummaryFromFinal(finalCoverage) {
  let totalStatements = 0;
  let coveredStatements = 0;
  let totalFunctions = 0;
  let coveredFunctions = 0;
  let totalBranches = 0;
  let coveredBranches = 0;
  let totalLines = 0;
  let coveredLines = 0;

  for (const file of Object.values(finalCoverage)) {
    totalStatements += Object.keys(file.statementMap).length;
    coveredStatements += Object.values(file.s).filter((count) => count > 0).length;

    totalFunctions += Object.keys(file.fnMap).length;
    coveredFunctions += Object.values(file.f).filter((count) => count > 0).length;

    totalLines += new Set(
      Object.values(file.statementMap).flatMap((location) =>
        Array.from(
          { length: location.end.line - location.start.line + 1 },
          (_, index) => location.start.line + index
        )
      )
    ).size;
    coveredLines += new Set(
      Object.entries(file.s)
        .filter(([, count]) => count > 0)
        .flatMap(([statementId]) => {
          const location = file.statementMap[statementId];
          return Array.from(
            { length: location.end.line - location.start.line + 1 },
            (_, index) => location.start.line + index
          );
        })
    ).size;

    totalBranches += Object.values(file.branchMap).reduce(
      (sum, branch) => sum + branch.locations.length,
      0
    );
    coveredBranches += Object.values(file.b).reduce(
      (sum, hits) => sum + hits.filter((count) => count > 0).length,
      0
    );
  }

  return {
    lines: percentage(coveredLines, totalLines),
    statements: percentage(coveredStatements, totalStatements),
    branches: percentage(coveredBranches, totalBranches),
    functions: percentage(coveredFunctions, totalFunctions),
  };
}

const totals = fs.existsSync(summaryPath)
  ? (() => {
      const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
      return {
        lines: Number(summary.total.lines.pct).toFixed(2),
        statements: Number(summary.total.statements.pct).toFixed(2),
        branches: Number(summary.total.branches.pct).toFixed(2),
        functions: Number(summary.total.functions.pct).toFixed(2),
      };
    })()
  : buildSummaryFromFinal(JSON.parse(fs.readFileSync(finalPath, "utf8")));

const { lines, statements, branches, functions } = totals;

function pickColor(value) {
  const num = Number(value);
  if (num >= 95) return "brightgreen";
  if (num >= 90) return "green";
  if (num >= 80) return "yellow";
  if (num >= 70) return "orange";
  return "red";
}

const badge = `![Coverage](https://img.shields.io/badge/coverage-${lines}%25-${pickColor(lines)})`;
const section = [
  "## Frontend Test Coverage",
  "",
  `${badge}`,
  "",
  "| Metric | Coverage |",
  "| --- | ---: |",
  `| Lines | ${lines}% |`,
  `| Statements | ${statements}% |`,
  `| Branches | ${branches}% |`,
  `| Functions | ${functions}% |`,
  "",
  "_This section reports frontend Jest coverage and is updated automatically by GitHub Actions._",
].join("\n");

const start = "<!-- coverage:start -->";
const end = "<!-- coverage:end -->";
const readme = fs.readFileSync(readmePath, "utf8");

if (!readme.includes(start) || !readme.includes(end)) {
  throw new Error("README coverage markers are missing.");
}

const next = readme.replace(
  new RegExp(`${start}[\\s\\S]*?${end}`),
  `${start}\n${section}\n${end}`
);

fs.writeFileSync(readmePath, next);
