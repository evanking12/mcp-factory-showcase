/**
 * sample.ts — Demo TypeScript module for MCP Factory js_analyzer tests.
 *
 * Exercises: exported typed functions, class methods, interface use,
 * async/await, JSDoc, and return-type annotations.
 */

import * as fs from 'fs';
import * as path from 'path';

// ──────────────────────────────────────────────────────────────────────
// Shared types
// ──────────────────────────────────────────────────────────────────────

export interface Invocable {
    name: string;
    signature: string;
    confidence: 'guaranteed' | 'high' | 'medium' | 'low';
    doc_comment?: string;
    parameters?: string;
    return_type?: string;
}

export interface McpPayload {
    source_file: string;
    analyzer:    string;
    invocables:  Invocable[];
}

// ──────────────────────────────────────────────────────────────────────
// Exported standalone functions
// ──────────────────────────────────────────────────────────────────────

/**
 * Read a file and return its content as a UTF-8 string.
 *
 * @param filePath - Absolute path to the target file.
 * @returns The file content.
 * @throws If the file does not exist or cannot be read.
 */
export function readTextFile(filePath: string): string {
    return fs.readFileSync(filePath, 'utf8');
}

/**
 * Score invocability confidence for an exported symbol.
 *
 * @param name     - Symbol name.
 * @param hasDoc   - Whether a docstring or header entry was found.
 * @param isSigned - Whether the binary carries a digital signature.
 * @returns A confidence label string.
 */
export function scoreConfidence(
    name:     string,
    hasDoc:   boolean,
    isSigned: boolean,
): Invocable['confidence'] {
    if (hasDoc && isSigned)       return 'guaranteed';
    if (hasDoc || isSigned)       return 'high';
    if (!name.startsWith('_'))    return 'medium';
    return 'low';
}

/**
 * Build and serialise a minimal MCP JSON payload.
 *
 * @param sourceFile  - The analysed file path (for metadata).
 * @param invocables  - Detected invocable entries.
 * @param indent      - JSON indentation width (default 2).
 * @returns Serialised JSON string.
 */
export function buildMcpJson(
    sourceFile: string,
    invocables: Invocable[],
    indent     = 2,
): string {
    const payload: McpPayload = {
        source_file: sourceFile,
        analyzer:    'js_analyzer',
        invocables,
    };
    return JSON.stringify(payload, null, indent);
}

// ──────────────────────────────────────────────────────────────────────
// Class with typed methods
// ──────────────────────────────────────────────────────────────────────

/**
 * High-level wrapper that analyses a single JS/TS source file.
 */
export class ScriptAnalyzer {
    private readonly filePath: string;

    constructor(filePath: string) {
        this.filePath = path.resolve(filePath);
    }

    /**
     * Read and return raw source text.
     *
     * @returns Source file contents as a string.
     */
    public readSource(): string {
        return readTextFile(this.filePath);
    }

    /**
     * Run the analysis pipeline.
     *
     * @param verbose - If true, log progress to stdout.
     * @returns Detected invocables.
     */
    public async analyse(verbose = false): Promise<Invocable[]> {
        if (verbose) console.log(`Analysing ${this.filePath}`);
        // Stub: real implementation calls regex engine
        return [];
    }

    /**
     * Write the MCP JSON output file.
     *
     * @param outDir  - Directory to write into.
     * @param results - Invocables to serialise.
     * @returns Path to the written file.
     */
    public writeOutput(outDir: string, results: Invocable[]): string {
        const name = path.basename(this.filePath, path.extname(this.filePath));
        const outPath = path.join(outDir, `${name}_mcp.json`);
        fs.writeFileSync(outPath, buildMcpJson(this.filePath, results));
        return outPath;
    }
}
