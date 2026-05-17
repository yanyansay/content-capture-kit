#!/usr/bin/env node
"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const packageRoot = path.resolve(__dirname, "..", "..");
const args = ["-m", "content_capture", ...process.argv.slice(2)];
const env = { ...process.env };
env.PYTHONPATH = env.PYTHONPATH ? `${packageRoot}${path.delimiter}${env.PYTHONPATH}` : packageRoot;

const candidates = process.platform === "win32" ? ["py -3", "python3", "python"] : ["python3", "python"];

for (const candidate of candidates) {
  const [command, ...prefixArgs] = candidate.split(" ");
  const result = spawnSync(command, [...prefixArgs, ...args], {
    cwd: process.cwd(),
    env,
    stdio: "inherit"
  });

  if (result.error && result.error.code === "ENOENT") {
    continue;
  }

  if (result.error) {
    console.error(`content-capture-kit failed to start ${command}: ${result.error.message}`);
    process.exit(1);
  }

  process.exit(result.status === null ? 1 : result.status);
}

console.error("content-capture-kit requires Python 3.11 or newer on PATH.");
process.exit(1);
