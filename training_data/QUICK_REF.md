# Quick Reference: extract_training_data_configurable.py

## 🚀 Quick Start Commands

```bash
# Use balanced preset (RECOMMENDED)
python extract_training_data_configurable.py --preset balanced

# Steven's 10K card config
python extract_training_data_configurable.py --preset steven-10k

# Show config without extracting
python extract_training_data_configurable.py --preset comprehensive --dry-run

# Custom configuration
python extract_training_data_configurable.py \
  --total 300000 \
  --tier1 4000 --tier2 2000 --tier3 1000 \
  --tier1-examples 25 --tier2-examples 18 --tier3-examples 12 \
  --card-pct 50 --combo-pct 20 --rules-pct 20 --articles-pct 7 --strategic-pct 3
```

## 📋 Available Presets

| Preset | Cards | Total | Time | Accuracy |
|--------|-------|-------|------|----------|
| quick | 2K | 50K | 4h | 93-95% |
| **balanced** | **5K** | **150K** | **36h** | **96-97%** ✅ |
| comprehensive | 10K | 600K | 180h | 98-99% |
| card-master | 8K | 400K | 120h | 97-98% |
| **steven-10k** | **10K** | **500K** | **150h** | **97-98%** ✅ |

See full documentation in CONFIGURABLE_EXTRACTION_GUIDE.md
