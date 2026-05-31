# Localize your game in one command

**localization-extractor** scans your Roblox Luau scripts for hardcoded user-facing
strings and auto-generates a localization table. No more copy-pasting 300+ strings
by hand.

## Why retroactive localization is the worst

You built your game. It has UI, shop text, notifications, dialog, HUD elements —
all hardcoded in English. Now you want to ship in Spanish, Portuguese, Japanese,
Korean… and you're staring down:

- **Manual extraction**: grep for `"text"`, skip debug `print()` calls, ignore
  file paths, filter out Roblox service names. For 47 files this might mean
  300+ strings to catalogue by hand.
- **Inconsistent keys**: you make up key names as you go. `shop_buy`,
  `shop_purchase`, `purchase_btn` — good luck remembering which is which.
- **No context for translators**: "Buy" could mean purchase, acquire, believe.
  Translators need to know it's on a button.
- **Format strings are tricky**: `"You have {coins} coins!"` needs special
  handling so translators can reorder the placeholders.

This tool does all of the above automatically.

## Usage

```bash
python localization-extractor.py --path src/
```

### Options

| Option | Default | Description |
|---|---|---|
| `--path` | *(required)* | Directory to scan for `.lua`/`.luau` files |
| `--output`, `-o` | `strings.csv` | Output file path |
| `--format` | `csv` | Output format: `csv` or `json` |
| `--key-prefix` | `str` | Prefix for auto-generated keys |
| `--min-length` | `3` | Minimum string length to extract |
| `--include-comments` | off | Also extract strings inside comments |
| `--verbose` | off | Show per-file processing details |

### Examples

```bash
# Basic scan, output CSV (for translators)
python localization-extractor.py --path src/ --output en_strings.csv

# JSON output (for automation/CI)
python localization-extractor.py --path src/ --format json --output strings.json

# Custom key prefix and minimum length
python localization-extractor.py --path src/ --key-prefix ui --min-length 5

# Scan including commented-out strings, with verbose output
python localization-extractor.py --path src/ --include-comments --verbose
```

## Extraction rules

The scanner finds string literals in these patterns:

- **Double/single quotes**: `"Hello World"`, `'Welcome'`
- **Multi-line strings**: `[[long text]]`, `[=[nested]=]`
- **GUI assignments**: `Text = "Hello"`, `TextLabel.Text = "Welcome"`
- **Format strings**: `string.format(...)` and concatenation `"Hello " .. name`

It automatically **skips**:

- Debug/log calls: `print("msg")`, `warn("msg")`, `error("msg")`
- Numeric strings: `"123"`, `"3.14"`
- Single characters: `"x"`
- Roblox service names: `"ServerScriptService"`, `"ReplicatedStorage"`
- `require()` paths
- Block comments: `--[[ ... ]]`
- `assert()` error messages that are just function names

## Output format

### CSV (default, for translators)

```csv
Key,SourceFile,Line,OriginalString,Context,ReplaceWith
greeting,MainMenu.luau,12,"Welcome to MyGame!",ShopFrame.Title,localization:format("greeting")
shop_buy,Shop.luau,45,"Buy Now",BuyButton.Text,localization:format("shop_buy")
coin_display,HUD.luau,78,"You have {coins} coins!",HUD.StatusText,localization:format("coin_display",{coins = coins})
```

Give this CSV to translators. They fill in a column per language. You import
those translations into your game.

### JSON (for automation/CI)

```json
{
  "strings": [
    {
      "key": "greeting",
      "file": "MainMenu.luau",
      "line": 12,
      "original": "Welcome to MyGame!",
      "context": "ShopFrame.Title",
      "is_format": false,
      "category": "GUI text"
    }
  ],
  "source_language": "en"
}
```

Useful for CI pipelines, translation APIs, or programmatic localization workflows.

## How to integrate with Roblox LocalizationService

1. **Extract strings**:
   ```bash
   python localization-extractor.py --path src/ --output en.csv
   ```

2. **Translate**: Send `en.csv` to translators. For each target language, add
   a column with the translated strings.

3. **Build a LocalizationTable**: Convert your translated CSV into a Roblox
   `LocalizationTable` instance, or use a ModuleScript that maps keys to
   translated strings per locale.

4. **Replace hardcoded strings**: In your Luau source, replace:
   ```lua
   -- Before
   ShopFrame.Title.Text = "Welcome to MyGame!"
   
   -- After
   ShopFrame.Title.Text = localization:format("greeting")
   ```

5. **Wire up LocalizationService**: Use `LocalizationService:GetTranslatorForPlayerAsync(player)`
   to get the correct locale at runtime. Pass the translator into your
   `localization:format()` wrapper.

## Example workflow

```
extract                      translate                    import
  ┌──────┐    en.csv    ┌─────────────┐   es.csv    ┌──────────────┐
  │ scan ├──────────────►│ translators ├─────────────►│ Localization │
  └──────┘              └──────┬──────┘  pt.csv     │   Service    │
                               ├────────────────────►│  (runtime)   │
                               │       ja.csv        └──────────────┘
                               └────────────────────►
```

1. `python localization-extractor.py --path src/ --output en.csv`
2. Send `en.csv` to translators → receive `es.csv`, `pt.csv`, `ja.csv`
3. Build localization tables from translated CSVs
4. Replace hardcoded strings using the `ReplaceWith` column
5. Ship your game in multiple languages
