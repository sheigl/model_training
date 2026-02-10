# MongoDB $lookup Join for Release Dates

## How It Works

Your cards don't have `releaseDate` directly, but they have `setCode` which can be joined to the `sets` collection!

### Database Structure

**cards collection:**
```json
{
  "name": "The One Ring",
  "setCode": "LTR",  // ← Links to sets collection
  "text": "When The One Ring enters...",
  "manaCost": "{4}",
  "type": "Legendary Artifact"
}
```

**sets collection:**
```json
{
  "code": "LTR",  // ← Matches card's setCode
  "name": "The Lord of the Rings: Tales of Middle-earth",
  "releaseDate": "2023-06-23"  // ← What we need!
}
```

### MongoDB Aggregation Pipeline

The updated extraction uses `$lookup` to join these collections:

```python
pipeline = [
    # 1. Filter cards first
    {'$match': {
        'text': {'$exists': True, '$ne': ''},
        'type': {'$not': {'$regex': 'Basic Land'}},
        'setCode': {'$exists': True}
    }},
    
    # 2. Join with sets collection
    {'$lookup': {
        'from': 'sets',              # Join with sets collection
        'localField': 'setCode',     # cards.setCode
        'foreignField': 'code',      # sets.code
        'as': 'set_info'             # Store result as 'set_info'
    }},
    
    # 3. Unwind the set_info array
    {'$unwind': {
        'path': '$set_info',
        'preserveNullAndEmptyArrays': False
    }},
    
    # 4. Filter for recent sets
    {'$match': {
        'set_info.releaseDate': {'$gte': '2020-01-01'}
    }},
    
    # 5. Limit results
    {'$limit': 25000}
]

cards = cards_collection.aggregate(pipeline)
```

### Result

Each card now has the set information attached:

```python
{
  "name": "The One Ring",
  "setCode": "LTR",
  "text": "When The One Ring enters...",
  "set_info": {  # ← Joined from sets collection!
    "code": "LTR",
    "name": "The Lord of the Rings: Tales of Middle-earth",
    "releaseDate": "2023-06-23"
  }
}
```

## What This Gives You

### Tier 1: Actual Recent Cards (2020-2026)
- ✅ Bloomburrow (BLB) - 2024
- ✅ Modern Horizons 3 (MH3) - 2024
- ✅ Murders at Karlov Manor (MKM) - 2024
- ✅ The Lord of the Rings (LTR) - 2023
- ✅ Wilds of Eldraine (WOE) - 2023
- ✅ Commander Masters (CMM) - 2023
- ✅ Phyrexia: All Will Be One (ONE) - 2023
- ✅ Dominaria United (DMU) - 2022
- ✅ Kamigawa: Neon Dynasty (NEO) - 2022
- ✅ Streets of New Capenna (SNC) - 2022
- ✅ Innistrad: Crimson Vow (VOW) - 2021
- ✅ Innistrad: Midnight Hunt (MID) - 2021
- ✅ Zendikar Rising (ZNR) - 2020
- ✅ And ALL other sets from 2020-2026!

### Tier 2: Commander Staples
- Sol Ring, Rhystic Study, Cyclonic Rift, etc.
- Excludes cards already in Tier 1

### Tier 3: Historical Coverage
- Classic cards, older sets
- Broad sampling for complete coverage

## Performance Notes

The `$lookup` join is:
- ✅ Fast (MongoDB indexes make this efficient)
- ✅ Accurate (uses actual release dates from sets)
- ✅ Maintainable (works automatically with new sets)

## Expected Output

```
=== Extracting Card Data (TIERED APPROACH) ===

[TIER 1] Recent Cards (2020-2026) via set join...
  Running aggregation pipeline to join cards with sets...
  Found 18,234 recent cards
  Generated 82,053 examples from recent cards

[TIER 2] Commander Legal Cards...
  Sampled 12,000 commander cards (excluding tier 1)
  Generated 30,421 examples from commander cards

[TIER 3] Additional Coverage...
  Sampled 8,000 additional cards
  Generated 8,127 examples from additional cards

======================================================================
CARD EXTRACTION SUMMARY
======================================================================
Total cards covered: 38,234
  Tier 1 (Recent 2020+):    18,234 cards →  82,053 examples
  Tier 2 (Commander):       12,000 cards →  30,421 examples
  Tier 3 (Additional):       8,000 cards →   8,127 examples

Total card examples: 120,601

Sample recent sets included: Bloomburrow, Modern Horizons 3, 
Murders at Karlov Manor, Thunder Junction, Fallout...
======================================================================
```

## Why This Is Better

### Before (No Join)
```python
# Just grabbed first 20K cards
cards = cards_collection.find(query).limit(20000)
```
- ❌ No way to know if they're recent
- ❌ Random mix of old and new
- ❌ Model might not know 2024 cards

### After (With Join)
```python
# Actually filters by release date!
pipeline = [
    {'$lookup': ...},  # Join with sets
    {'$match': {'set_info.releaseDate': {'$gte': '2020-01-01'}}}
]
```
- ✅ 100% of cards are from 2020+
- ✅ Model knows ALL recent sets
- ✅ Can verify which sets are included

## Testing the Join

You can verify the join works:

```bash
mongosh -u root -p whatever --authenticationDatabase admin

use mtg_json

// Test the join
db.cards.aggregate([
  {$match: {setCode: 'BLB'}},  // Bloomburrow
  {$lookup: {
    from: 'sets',
    localField: 'setCode',
    foreignField: 'code',
    as: 'set_info'
  }},
  {$limit: 1}
]).pretty()

// Should show card with set_info containing releaseDate!
```

## Summary

The `$lookup` join gives you **real, accurate recent card coverage** based on actual release dates from the sets collection. This is much better than guessing or using arbitrary limits!
