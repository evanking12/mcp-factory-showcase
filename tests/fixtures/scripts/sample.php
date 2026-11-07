<?php
/**
 * sample.php — Demo PHP script for MCP Factory script_analyzer tests.
 *
 * Contains standalone functions and a class with PHPDoc to exercise
 * the PHP extraction path.
 */

declare(strict_types=1);

/**
 * Compress a file using gzencode.
 *
 * @param string $sourcePath Path to the source file.
 * @param string $destPath   Path for the compressed output.
 * @param int    $level      Compression level 1–9 (default 6).
 *
 * @return int Number of bytes written.
 */
function compress_file(string $sourcePath, string $destPath, int $level = 6): int
{
    $data = file_get_contents($sourcePath);
    $compressed = gzencode($data, $level);
    file_put_contents($destPath, $compressed);
    return strlen($compressed);
}

/**
 * Return exported symbol names from a PE DLL.
 *
 * @param string      $dllPath      Full path to the DLL.
 * @param string|null $filterPrefix Only return symbols with this prefix.
 *
 * @return string[]
 */
function list_exports(string $dllPath, ?string $filterPrefix = null): array
{
    $output = shell_exec("dumpbin /exports \"$dllPath\" 2>&1");
    preg_match_all('/\s+\d+\s+\w+\s+\w+\s+(\S+)/', $output ?? '', $matches);
    $symbols = $matches[1] ?? [];
    if ($filterPrefix !== null) {
        $symbols = array_filter($symbols, fn($s) => str_starts_with($s, $filterPrefix));
    }
    return array_values($symbols);
}

/**
 * Score invocability confidence for an export.
 *
 * @param string $name     Symbol name.
 * @param bool   $hasDoc   Whether a docstring/header was found.
 * @param bool   $isSigned Whether the binary is signed.
 *
 * @return string One of 'guaranteed', 'high', 'medium', 'low'.
 */
function score_confidence(string $name, bool $hasDoc, bool $isSigned): string
{
    if ($hasDoc && $isSigned) return 'guaranteed';
    if ($hasDoc || $isSigned) return 'high';
    if (!str_starts_with($name, '_')) return 'medium';
    return 'low';
}

/**
 * Analyse a single binary target.
 */
class BinaryAnalyzer
{
    public function __construct(private readonly string $path) {}

    /**
     * Run the full analysis pipeline.
     *
     * @return array<string, mixed>
     */
    public function run(): array
    {
        return ['path' => $this->path, 'invocables' => []];
    }

    /**
     * Serialise results to a JSON string.
     *
     * @param int $flags json_encode flags (default JSON_PRETTY_PRINT).
     *
     * @return string
     */
    public function toJson(int $flags = JSON_PRETTY_PRINT): string
    {
        return json_encode($this->run(), $flags);
    }
}
