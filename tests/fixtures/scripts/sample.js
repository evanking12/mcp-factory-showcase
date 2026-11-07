/**
 * sample.js — Demo JavaScript module for MCP Factory js_analyzer tests.
 *
 * Exercises: named functions, arrow functions, CommonJS exports,
 * JSDoc @param/@returns annotations, and CLI entry-point heuristics.
 */

'use strict';

// ──────────────────────────────────────────────────────────────────────
// Named function declarations
// ──────────────────────────────────────────────────────────────────────

/**
 * Compress a Buffer using the built-in zlib module.
 *
 * @param {Buffer} input     - Data to compress.
 * @param {number} [level=6] - zlib compression level (0–9).
 * @returns {Promise<Buffer>} Compressed output buffer.
 */
async function compressBuffer(input, level = 6) {
    const zlib = require('zlib');
    return new Promise((resolve, reject) => {
        zlib.gzip(input, { level }, (err, result) => {
            if (err) reject(err);
            else resolve(result);
        });
    });
}

/**
 * Parse exported symbol names from dumpbin stdout.
 *
 * @param {string} dumpbinOutput - Raw stdout from `dumpbin /exports`.
 * @param {string} [prefix]      - Optional symbol prefix filter.
 * @returns {string[]} Array of matched symbol names.
 */
function parseExports(dumpbinOutput, prefix) {
    const lines = dumpbinOutput.split('\n');
    const symbols = [];
    for (const line of lines) {
        const m = line.match(/^\s+\d+\s+\w+\s+\w+\s+(\S+)/);
        if (m) symbols.push(m[1]);
    }
    return prefix ? symbols.filter(s => s.startsWith(prefix)) : symbols;
}

// ──────────────────────────────────────────────────────────────────────
// Arrow function assigned to const
// ──────────────────────────────────────────────────────────────────────

/**
 * Score invocability confidence for an exported symbol.
 *
 * @param {string}  name     - Symbol name.
 * @param {boolean} hasDoc   - Whether a header/docstring was found.
 * @param {boolean} isSigned - Whether the binary is digitally signed.
 * @returns {'guaranteed'|'high'|'medium'|'low'} Confidence label.
 */
const scoreConfidence = (name, hasDoc, isSigned) => {
    if (hasDoc && isSigned) return 'guaranteed';
    if (hasDoc || isSigned) return 'high';
    if (!name.startsWith('_'))  return 'medium';
    return 'low';
};

/**
 * Build a minimal MCP JSON payload from an array of invocable objects.
 *
 * @param {Array<{name: string, signature: string, confidence: string}>} invocables
 * @param {number} [indent=2] - JSON indentation width.
 * @returns {string} Serialised JSON.
 */
const buildMcpJson = (invocables, indent = 2) =>
    JSON.stringify({ invocables }, null, indent);

// ──────────────────────────────────────────────────────────────────────
// CommonJS named exports
// ──────────────────────────────────────────────────────────────────────

/**
 * Deduplicate an array of symbol names (case-sensitive).
 *
 * @param {string[]} names - Input symbol name array.
 * @returns {string[]} De-duplicated array preserving first-occurrence order.
 */
module.exports.deduplicateExports = function deduplicateExports(names) {
    return [...new Set(names)];
};

/**
 * Format a confidence label as an upper-case badge string.
 *
 * @param {string} label - e.g. 'guaranteed'
 * @returns {string} e.g. '[GUARANTEED]'
 */
exports.formatConfidenceBadge = (label) => `[${label.toUpperCase()}]`;

// ──────────────────────────────────────────────────────────────────────
// CLI entry-point  (process.argv triggers CLI detection heuristic)
// ──────────────────────────────────────────────────────────────────────
if (require.main === module) {
    const [,, inputFile] = process.argv;
    if (!inputFile) {
        console.error('Usage: node sample.js <dll-path>');
        process.exit(1);
    }
    // Demo: read file, pretend to parse
    const fs = require('fs');
    const raw = fs.readFileSync(inputFile, 'utf8');
    const symbols = parseExports(raw);
    console.log(JSON.stringify(symbols, null, 2));
}
