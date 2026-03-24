import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const coverageDir = path.join(repoRoot, "frontend", "coverage");
const summaryPath = path.join(coverageDir, "coverage-summary.json");
const finalPath = path.join(coverageDir, "coverage-final.json");
const readmePath = path.join(repoRoot, "README.md");

function percentage(covered, total) {
  if (total === 0) {
    return "100.00";
  }

  return ((covered / total) * 100).toFixed(2);
}

function buildSummaryFromFinal(finalCoverage) {
  let totalLines = 0;
  let coveredLines = 0;

  for (const file of Object.values(finalCoverage)) {
    const allLines = new Set(
      Object.values(file.statementMap).flatMap((location) =>
        Array.from(
          { length: location.end.line - location.start.line + 1 },
          (_, index) => location.start.line + index
        )
      )
    );

    const hitLines = new Set(
      Object.entries(file.s)
        .filter(([, count]) => count > 0)
        .flatMap(([statementId]) => {
          const location = file.statementMap[statementId];
          return Array.from(
            { length: location.end.line - location.start.line + 1 },
            (_, index) => location.start.line + index
          );
        })
    );

    totalLines += allLines.size;
    coveredLines += hitLines.size;
  }

  return { lines: percentage(coveredLines, totalLines) };
}

function getCoverage() {
  if (fs.existsSync(summaryPath)) {
    const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
    return Number(summary.total.lines.pct).toFixed(2);
  }

  if (fs.existsSync(finalPath)) {
    return buildSummaryFromFinal(JSON.parse(fs.readFileSync(finalPath, "utf8"))).lines;
  }

  throw new Error(
    `No coverage summary found. Expected ${summaryPath} or ${finalPath}.`
  );
}

function badgeColor(linesCoverage) {
  const lines = Number(linesCoverage);
  if (lines >= 90) return "brightgreen";
  if (lines >= 80) return "green";
  if (lines >= 70) return "yellow";
  if (lines >= 60) return "orange";
  return "red";
}

const markerStart = "<!-- frontend-coverage-start -->";
const markerEnd = "<!-- frontend-coverage-end -->";
const lines = getCoverage();
const color = badgeColor(lines);
const badge = `![Frontend coverage](https://img.shields.io/badge/frontend%20coverage-${lines}%25-${color})`;
const replacement = `${markerStart}\n${badge}\n${markerEnd}`;

const readme = fs.readFileSync(readmePath, "utf8");
const markerRegex = new RegExp(`${markerStart}[\\s\\S]*?${markerEnd}`);
const nextReadme = markerRegex.test(readme)
  ? readme.replace(markerRegex, replacement)
  : `${readme.trimEnd()}\n\n${replacement}\n`;

fs.writeFileSync(readmePath, `${nextReadme.endsWith("\n") ? nextReadme : `${nextReadme}\n`}`);
