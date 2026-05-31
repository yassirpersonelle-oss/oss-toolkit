# Changelog

## [1.0.0] — 2026-06-01

### Added
- Claude Desktop direct output format (`--format claude`)
- Interactive mode (`--interactive`) for selecting which functions to expose
- MCP server wrapper generation (`--generate-server`)
- Auto-detection of project entry points from package.json, pyproject.toml, Cargo.toml
- Enhanced docstring parsing with @param/@returns/@example tag extraction
- `--exclude` pattern for filtering functions by regex
- `--show-all` flag to include test/internal functions

### Changed
- Improved JSDoc comment extraction for JavaScript/TypeScript
- Better Python type annotation mapping (Optional, Union, Literal)
- Refined route detection for FastAPI decorators with multiple HTTP methods

### Fixed
- Handle files with BOM encoding properly
- Skip virtual environment directories during scan
- Don't crash on syntax errors in individual files (continue scanning)

## [0.2.0] — 2026-05-25

### Added
- Rust language support (`pub fn` detection)
- Go language support (exported function detection)
- Route pattern detection for Express/Fastify
- --stdout flag for piping output
- Individual tool JSON file output

### Changed
- Faster directory scanning with early skip logic
- More accurate JS/TS parameter extraction

## [0.1.0] — 2026-05-20

### Added
- Initial release
- Python function discovery via AST
- JavaScript/TypeScript function discovery via regex
- MCP config JSON generation
- Auto language detection from file extensions
- Basic type mapping (str→string, int→integer, bool→boolean)
