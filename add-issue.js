#!/usr/bin/env node
/**
 * Add a new issue to the PPU archive and rebuild the site.
 *
 * Usage:
 *   node add-issue.js new-issue.json              # merge + rebuild
 *   node add-issue.js new-issue.json --no-build   # merge only, skip rebuild
 *
 * The input JSON can be:
 *   - A single edition object: { "edition": "...", "articles": [...] }
 *   - An array of editions:    [{ "edition": "...", "articles": [...] }, ...]
 *
 * Articles are matched by PMID to avoid duplicates. If an edition already
 * exists, new articles are appended (existing ones are updated in place).
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const ARCHIVE_PATH = path.join(__dirname, "ppu_archive.json");

function main() {
  const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
  const flags = process.argv.slice(2).filter((a) => a.startsWith("--"));
  const skipBuild = flags.includes("--no-build");

  if (args.length === 0) {
    console.error("Usage: node add-issue.js <new-issue.json> [--no-build]");
    process.exit(1);
  }

  const inputPath = path.resolve(args[0]);
  if (!fs.existsSync(inputPath)) {
    console.error(`File not found: ${inputPath}`);
    process.exit(1);
  }

  // Read input
  let input;
  try {
    input = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
  } catch (e) {
    console.error(`Failed to parse ${inputPath}: ${e.message}`);
    process.exit(1);
  }

  // Normalize to array of editions
  const newEditions = Array.isArray(input) ? input : [input];

  // Validate
  for (const ed of newEditions) {
    if (!ed.edition || !Array.isArray(ed.articles)) {
      console.error(
        `Invalid edition object — must have "edition" (string) and "articles" (array).`
      );
      console.error(`Got keys: ${Object.keys(ed).join(", ")}`);
      process.exit(1);
    }
  }

  // Read existing archive
  let archive = [];
  if (fs.existsSync(ARCHIVE_PATH)) {
    archive = JSON.parse(fs.readFileSync(ARCHIVE_PATH, "utf-8"));
  }

  // Merge
  let addedEditions = 0;
  let addedArticles = 0;
  let updatedArticles = 0;

  for (const newEd of newEditions) {
    const existing = archive.find(
      (e) => e.edition.toLowerCase() === newEd.edition.toLowerCase()
    );

    if (existing) {
      // Merge articles into existing edition
      const existingPmids = new Map(
        existing.articles
          .filter((a) => a.pmid)
          .map((a) => [a.pmid, a])
      );

      for (const article of newEd.articles) {
        if (article.pmid && existingPmids.has(article.pmid)) {
          // Update existing article in place
          const idx = existing.articles.indexOf(existingPmids.get(article.pmid));
          existing.articles[idx] = { ...existing.articles[idx], ...article };
          updatedArticles++;
        } else {
          existing.articles.push(article);
          addedArticles++;
        }
      }
      existing.article_count = existing.articles.length;
      console.log(
        `Updated "${existing.edition}": ${existing.article_count} articles total`
      );
    } else {
      // New edition
      const edition = {
        edition: newEd.edition,
        filename: newEd.filename || "",
        article_count: newEd.articles.length,
        articles: newEd.articles,
      };
      archive.push(edition);
      addedEditions++;
      addedArticles += newEd.articles.length;
      console.log(
        `Added new edition "${edition.edition}" with ${edition.article_count} articles`
      );
    }
  }

  // Write updated archive
  fs.writeFileSync(ARCHIVE_PATH, JSON.stringify(archive, null, 2), "utf-8");

  const totalArticles = archive.reduce((n, e) => n + e.article_count, 0);
  console.log(
    `\nArchive now has ${archive.length} editions, ${totalArticles} articles total.`
  );
  if (addedEditions) console.log(`  New editions: ${addedEditions}`);
  if (addedArticles) console.log(`  New articles: ${addedArticles}`);
  if (updatedArticles) console.log(`  Updated articles: ${updatedArticles}`);

  // Rebuild
  if (!skipBuild) {
    console.log("\nRebuilding site...");
    try {
      execSync("python3 build.py", { cwd: __dirname, stdio: "inherit" });
      console.log("\nDone! Preview at dist/index.html");
    } catch (e) {
      console.error("Build failed:", e.message);
      process.exit(1);
    }
  } else {
    console.log("\nSkipped build (--no-build). Run `python3 build.py` to rebuild.");
  }
}

main();
