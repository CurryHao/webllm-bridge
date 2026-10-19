# UI baselines

Baseline screenshots for the preflight UI check live here:

- `<provider>-small.png` (viewport 1280x800)
- `<provider>-large.png` (viewport 1920x1080)

Generate or refresh them with:

```powershell
python main.py --provider deepseek --check --update-baseline
```

The preflight check masks each provider's `dynamic_selectors` before diffing, but the
screenshots can still include account-specific chrome such as the sidebar or recent
conversation titles. Review a baseline before committing it, and refresh it whenever the
provider ships a UI update.
