# sample.rb — Demo Ruby script for MCP Factory script_analyzer tests.
#
# Contains standalone methods, a module, and a class to exercise
# the `def` extraction path.

require 'json'
require 'pathname'

# Compress *source* into *dest* via zlib.
# @param source [String] path to the source file
# @param dest   [String] path for compressed output
# @param level  [Integer] compression level 1–9
# @return       [Integer] bytes written
def compress_file(source, dest, level = 6)
  data = File.binread(source)
  File.binwrite(dest, data)   # placeholder
  data.length
end

# Return exported symbol names from a PE DLL via dumpbin.
# @param dll_path      [String] path to the DLL
# @param filter_prefix [String, nil] optional symbol prefix filter
# @return              [Array<String>]
def list_exports(dll_path, filter_prefix = nil)
  output = `dumpbin /exports "#{dll_path}" 2>&1`
  symbols = output.scan(/\s+\d+\s+\w+\s+\w+\s+(\S+)/).flatten
  filter_prefix ? symbols.select { |s| s.start_with?(filter_prefix) } : symbols
end

# Assign an invocability confidence label.
# @param name     [String]
# @param has_doc  [Boolean]
# @param is_signed [Boolean]
# @return [String] one of 'guaranteed', 'high', 'medium', 'low'
def score_confidence(name, has_doc, is_signed)
  return 'guaranteed' if has_doc && is_signed
  return 'high'       if has_doc || is_signed
  return 'medium'     unless name.start_with?('_')
  'low'
end

module McpFactory
  # Write an MCP JSON payload to *path*.
  # @param invocables [Array<Hash>]
  # @param path       [String]
  def self.write_mcp_json(invocables, path)
    payload = { invocables: invocables }
    File.write(path, JSON.pretty_generate(payload))
  end
end

class BinaryAnalyzer
  attr_reader :path

  def initialize(path)
    @path = Pathname.new(path)
  end

  # Run the full analysis pipeline.
  # @return [Hash] analysis results
  def run
    { path: @path.to_s, invocables: [] }
  end

  # Serialise results to JSON.
  # @param indent [Integer] indentation spaces
  # @return       [String]
  def to_json(indent: 2)
    JSON.pretty_generate(run)
  end
end
