import re
import pymongo
from datetime import datetime
from typing import Optional, Any

class ScryfallSearchResults:
    def __init__(self, search_query: str, result_count: int, cards: list[dict]):
        self.search_query = search_query
        self.result_count = result_count
        self.cards = cards

class ScryfallMongo:
    def __init__(self, client: pymongo.MongoClient):
        self.citation = False
        self.client = client

    # ─── Tokenizer ────────────────────────────────────────────────────────────

    def _read_value(self, query: str, pos: int):
        """Read a quoted or bare value starting at pos. Returns (value, new_pos)."""
        if pos >= len(query):
            return "", pos
        if query[pos] in ('"', "'"):
            quote = query[pos]
            end = query.find(quote, pos + 1)
            if end == -1:
                end = len(query)
            return query[pos + 1 : end], end + 1
        m = re.match(r"([^\s()]+)", query[pos:])
        return (m.group(1), pos + len(m.group(1))) if m else ("", pos)

    def _tokenize(self, query: str) -> list:
        """
        Tokenize a Scryfall-like query string into a list of token dicts.

        Token types:
          PAREN  — '(' or ')'
          OP     — 'AND', 'OR', 'NOT'
          FILTER — key + operator + value  (e.g. t:creature, cmc<=3)
          NAME   — bare word / quoted phrase (generic text search)
        """
        tokens = []
        i = 0
        query = query.strip()

        while i < len(query):
            if query[i].isspace():
                i += 1
                continue

            if query[i] in "()":
                tokens.append({"type": "PAREN", "value": query[i]})
                i += 1
                continue

            # Exact name prefix: !"Lightning Bolt" or !bolt
            if query[i] == "!" and (i + 1 >= len(query) or query[i + 1] != "="):
                i += 1
                value, i = self._read_value(query, i)
                if value:
                    tokens.append(
                        {"type": "FILTER", "key": "name", "op": "!", "value": value, "negated": False}
                    )
                continue

            # Optional leading negation dash
            negated = query[i] == "-"
            if negated:
                i += 1
                if i >= len(query):
                    break

            # key:value  /  key=value  /  key<=value  etc.
            m = re.match(r"(\w+)([:=!<>]=?|<|>)", query[i:])
            if m:
                key = m.group(1).lower()
                op = m.group(2)
                j = i + len(m.group(0))
                # Don't treat AND/OR/NOT as filter keys
                if key.upper() not in ("AND", "OR", "NOT") or op != ":":
                    value, j = self._read_value(query, j)
                    tokens.append(
                        {
                            "type": "FILTER",
                            "key": key,
                            "op": op,
                            "value": value,
                            "negated": negated,
                        }
                    )
                    i = j
                    continue
                else:
                    # Back out negation — treat as logical op on next pass
                    if negated:
                        i -= 1
                        negated = False

            # Logical operators (only when not negated)
            if not negated:
                m = re.match(r"(AND|OR|NOT)\b", query[i:], re.IGNORECASE)
                if m and m.group(1).upper() in ("AND", "OR", "NOT"):
                    tokens.append({"type": "OP", "value": m.group(1).upper()})
                    i += len(m.group(1))
                    continue

            # Quoted string
            if i < len(query) and query[i] in ('"', "'"):
                value, i = self._read_value(query, i)
                tokens.append({"type": "NAME", "value": value, "negated": negated})
                continue

            # Bare word
            m = re.match(r"([^\s()]+)", query[i:])
            if m:
                tokens.append({"type": "NAME", "value": m.group(1), "negated": negated})
                i += len(m.group(1))
                continue

            i += 1

        return tokens

    # ─── Query builders ───────────────────────────────────────────────────────

    _COLOR_MAP = {"w": "W", "u": "U", "b": "B", "r": "R", "g": "G", "c": "C"}
    _ALL_COLORS = ["W", "U", "B", "R", "G"]

    def _maybe_negate(self, q: dict, negated: bool) -> dict:
        if not q:
            return {}
        return {"$nor": [q]} if negated else q

    def _color_query(self, field: str, op: str, value: str, negated: bool) -> dict:
        v = value.lower()

        if v == "colorless":
            q = {field: []}
        elif v in ("m", "multi", "multicolor", "multicolored"):
            q = {"$expr": {"$gt": [{"$size": f"${field}"}, 1]}}
        elif v in ("mono", "monocolored"):
            q = {"$expr": {"$eq": [{"$size": f"${field}"}, 1]}}
        else:
            colors = [self._COLOR_MAP[c] for c in v if c in self._COLOR_MAP]
            if not colors:
                return {}
            if op in (":", ">="):
                # Contains at least these colors
                q = {field: {"$all": colors}}
            elif op == "=":
                # Exactly these colors
                q = {
                    "$and": [
                        {field: {"$all": colors}},
                        {"$expr": {"$eq": [{"$size": f"${field}"}, len(colors)]}},
                    ]
                }
            elif op == "<=":
                # Subset — no color outside the allowed set
                outside = [c for c in self._ALL_COLORS if c not in colors]
                q = {field: {"$nin": outside}} if outside else {}
            elif op == "<":
                # Proper subset
                outside = [c for c in self._ALL_COLORS if c not in colors]
                parts = [{field: {"$nin": outside}}] if outside else []
                parts.append({"$expr": {"$lt": [{"$size": f"${field}"}, len(colors)]}})
                q = {"$and": parts}
            elif op == ">":
                # Strict superset
                q = {
                    "$and": [
                        {field: {"$all": colors}},
                        {"$expr": {"$gt": [{"$size": f"${field}"}, len(colors)]}},
                    ]
                }
            else:
                q = {field: {"$all": colors}}

        return self._maybe_negate(q, negated)

    def _numeric_query(
        self, field: str, op: str, value: str, negated: bool, string_field: bool = False
    ) -> dict:
        """
        Build a numeric comparison query. string_field=True is used for power/toughness
        which are stored as strings in Scryfall data (e.g. "2", "*", "1+*").
        Supports 'even' and 'odd' as special values for integer fields.
        """
        v = value.lower()
        if v in ("even", "odd"):
            remainder = 0 if v == "even" else 1
            q = {"$expr": {"$eq": [{"$mod": [f"${field}", 2]}, remainder]}}
            return self._maybe_negate(q, negated)

        try:
            num = float(value)
        except ValueError:
            return {}

        op_map = {
            ":": "$eq", "=": "$eq",
            "<": "$lt", "<=": "$lte",
            ">": "$gt", ">=": "$gte",
            "!=": "$ne",
        }
        mongo_op = op_map.get(op, "$eq")

        if string_field:
            # $convert with onError so non-numeric values ("*") don't crash the query
            q = {
                "$expr": {
                    mongo_op: [
                        {
                            "$convert": {
                                "input": f"${field}",
                                "to": "double",
                                "onError": -999,
                                "onNull": -999,
                            }
                        },
                        num,
                    ]
                }
            }
        else:
            q = {field: {mongo_op: num}}

        return self._maybe_negate(q, negated)

    def _text_query(self, fields, value: str, negated: bool) -> dict:
        """Case-insensitive regex search across one or more fields."""
        if isinstance(fields, str):
            fields = [fields]
        regex = {"$regex": re.escape(value), "$options": "i"}
        q = (
            {fields[0]: regex}
            if len(fields) == 1
            else {"$or": [{f: regex} for f in fields]}
        )
        return self._maybe_negate(q, negated)

    def _exact_query(self, field: str, value: str, negated: bool) -> dict:
        return self._maybe_negate({field: value}, negated)

    def _mana_query(self, field: str, op: str, value: str, negated: bool) -> dict:
        """
        Filter on mana cost symbols (e.g. mana={W}, mana:{U}{U}, mana={0}).
        Values are Scryfall symbol notation like {W}, {2}, {C}, {X}, etc.

        '='        → exact mana cost (anchored match)
        ':' / '>=' → mana cost contains the given symbol(s)
        other ops  → fallback to contains
        """
        escaped = re.escape(value)
        if op == "=":
            q = {field: {"$regex": f"^{escaped}$", "$options": "i"}}
        else:
            q = {field: {"$regex": escaped, "$options": "i"}}
        return self._maybe_negate(q, negated)

    def _price_query(self, price_field: str, op: str, value: str, negated: bool) -> dict:
        """
        Numeric comparison on a prices sub-field (e.g. prices.usd).
        Prices are stored as strings ("1.23") or null in Scryfall data.
        """
        try:
            num = float(value)
        except ValueError:
            return {}
        op_map = {
            ":": "$eq", "=": "$eq",
            "<": "$lt", "<=": "$lte",
            ">": "$gt", ">=": "$gte",
            "!=": "$ne",
        }
        mongo_op = op_map.get(op, "$eq")
        q = {
            "$expr": {
                mongo_op: [
                    {
                        "$convert": {
                            "input": f"${price_field}",
                            "to": "double",
                            "onError": -1,
                            "onNull": -1,
                        }
                    },
                    num,
                ]
            }
        }
        return self._maybe_negate(q, negated)

    def _year_query(self, op: str, value: str, negated: bool) -> dict:
        """
        Filter by release year. Extracts the 4-digit year prefix from
        the 'released_at' field which is stored as 'YYYY-MM-DD'.
        """
        try:
            year = int(value)
        except ValueError:
            return {}
        op_map = {
            ":": "$eq", "=": "$eq",
            "<": "$lt", "<=": "$lte",
            ">": "$gt", ">=": "$gte",
            "!=": "$ne",
        }
        mongo_op = op_map.get(op, "$eq")
        q = {
            "$expr": {
                mongo_op: [
                    {"$toInt": {"$substr": ["$released_at", 0, 4]}},
                    year,
                ]
            }
        }
        return self._maybe_negate(q, negated)

    def _date_query(self, op: str, value: str, negated: bool) -> dict:
        """
        Filter by release date. 'released_at' is stored as 'YYYY-MM-DD' strings,
        so lexicographic comparison is equivalent to chronological comparison.
        """
        op_map = {
            ":": "$eq", "=": "$eq",
            "<": "$lt", "<=": "$lte",
            ">": "$gt", ">=": "$gte",
            "!=": "$ne",
        }
        mongo_op = op_map.get(op, "$eq")
        return self._maybe_negate({"released_at": {mongo_op: value}}, negated)

    def _is_query(self, value: str, negated: bool) -> dict:
        v = value.lower()
        mapping = {
            # ── Card types ────────────────────────────────────────────────────
            "legendary":    {"type_line": {"$regex": r"\bLegendary\b",    "$options": "i"}},
            "creature":     {"type_line": {"$regex": r"\bCreature\b",     "$options": "i"}},
            "artifact":     {"type_line": {"$regex": r"\bArtifact\b",     "$options": "i"}},
            "enchantment":  {"type_line": {"$regex": r"\bEnchantment\b",  "$options": "i"}},
            "instant":      {"type_line": {"$regex": r"\bInstant\b",      "$options": "i"}},
            "sorcery":      {"type_line": {"$regex": r"\bSorcery\b",      "$options": "i"}},
            "planeswalker": {"type_line": {"$regex": r"\bPlaneswalker\b", "$options": "i"}},
            "land":         {"type_line": {"$regex": r"\bLand\b",         "$options": "i"}},
            "basic":        {"type_line": {"$regex": r"\bBasic\b",        "$options": "i"}},
            "saga":         {"type_line": {"$regex": r"\bSaga\b",         "$options": "i"}},
            "battle":       {"type_line": {"$regex": r"\bBattle\b",       "$options": "i"}},
            "token":        {"layout": "token"},

            # ── Spell / permanent ─────────────────────────────────────────────
            "spell": {
                "$nor": [{"type_line": {"$regex": r"\bLand\b", "$options": "i"}}]
            },
            "permanent": {
                "type_line": {
                    "$regex": r"\b(Artifact|Creature|Enchantment|Land|Planeswalker|Battle)\b",
                    "$options": "i",
                }
            },
            "nonpermanent": {
                "type_line": {"$regex": r"\b(Instant|Sorcery)\b", "$options": "i"}
            },

            # ── Gameplay categories ───────────────────────────────────────────
            "historic": {
                "type_line": {
                    "$regex": r"\b(Legendary|Artifact|Saga)\b",
                    "$options": "i",
                }
            },
            "party": {
                "type_line": {
                    "$regex": r"\b(Cleric|Rogue|Warrior|Wizard)\b",
                    "$options": "i",
                }
            },
            "outlaw": {
                "type_line": {
                    "$regex": r"\b(Assassin|Mercenary|Pirate|Rogue|Warlock)\b",
                    "$options": "i",
                }
            },
            "commander": {
                "$or": [
                    {
                        "$and": [
                            {"type_line": {"$regex": r"\bLegendary\b", "$options": "i"}},
                            {"type_line": {"$regex": r"\bCreature\b",  "$options": "i"}},
                        ]
                    },
                    {"type_line": {"$regex": r"\bPlaneswalker\b", "$options": "i"}},
                ]
            },

            # ── Creature complexity ───────────────────────────────────────────
            "vanilla": {
                "$and": [
                    {"type_line": {"$regex": r"\bCreature\b", "$options": "i"}},
                    {"$or": [{"oracle_text": ""}, {"oracle_text": {"$exists": False}}]},
                ]
            },
            # Approximation: creature with no activated abilities ({...}:),
            # no triggered/static ability dashes (—), and no colons
            "frenchvanilla": {
                "$and": [
                    {"type_line": {"$regex": r"\bCreature\b", "$options": "i"}},
                    {"$nor": [{"oracle_text": {"$regex": r"[:{]|\u2014"}}]},
                ]
            },

            # ── Mana symbol types ─────────────────────────────────────────────
            "hybrid": {
                "mana_cost": {"$regex": r"\{[WUBRG2]/[WUBRG]\}", "$options": "i"}
            },
            "phyrexian": {
                "mana_cost": {"$regex": r"\{[WUBRG2]/P\}", "$options": "i"}
            },

            # ── Layouts ───────────────────────────────────────────────────────
            "split":     {"layout": "split"},
            "flip":      {"layout": "flip"},
            "transform": {"layout": "transform"},
            "mdfc":      {"layout": "modal_dfc"},
            "meld":      {"layout": "meld"},
            "meldpart":  {"layout": "meld"},
            "meldresult": {"layout": "meld"},
            "leveler":   {"layout": "leveler"},
            "adventure": {"layout": "adventure"},
            "dfc": {
                "layout": {"$in": ["transform", "modal_dfc", "double_faced_token"]}
            },

            # ── Keywords / mechanics ──────────────────────────────────────────
            "companion": {"keywords": {"$regex": r"^Companion$",  "$options": "i"}},
            "partner":   {"keywords": {"$regex": r"^Partner",     "$options": "i"}},

            # ── Color ─────────────────────────────────────────────────────────
            "multicolor":   {"$expr": {"$gt": [{"$size": "$colors"}, 1]}},
            "multicolored": {"$expr": {"$gt": [{"$size": "$colors"}, 1]}},
            "colorless":    {"colors": []},
            "monocolored":  {"$expr": {"$eq": [{"$size": "$colors"}, 1]}},

            # ── Printing / physical properties ────────────────────────────────
            "fullart":    {"full_art": True},
            "full_art":   {"full_art": True},
            "foil":       {"foil": True},
            "nonfoil":    {"nonfoil": True},
            "etched":     {"finishes": "etched"},
            "textless":   {"textless": True},
            "oversized":  {"oversized": True},
            "spotlight":  {"story_spotlight": True},
            "reserved":   {"reserved": True},
            "reprint":    {"reprint": True},
            "promo":      {"promo": True},
            "digital":    {"digital": True},
            "booster":    {"booster": True},

            # ── has: targets ──────────────────────────────────────────────────
            "watermark": {"watermark": {"$exists": True, "$nin": [None, ""]}},
            "indicator":  {"color_indicator": {"$exists": True, "$ne": None}},
        }
        q = mapping.get(v, {})
        if not q:
            return {}
        return self._maybe_negate(q, negated)

    def _filter_to_mongo(self, key: str, op: str, value: str, negated: bool) -> dict:
        # ── Color / identity ──────────────────────────────────────────────────
        if key in ("c", "color", "colour"):
            return self._color_query("colors", op, value, negated)
        if key in ("id", "identity", "ci"):
            return self._color_query("color_identity", op, value, negated)

        # ── Mana cost symbols ─────────────────────────────────────────────────
        if key in ("m", "mana", "manacost"):
            return self._mana_query("mana_cost", op, value, negated)

        # ── Numeric: mana value / CMC (supports even/odd) ─────────────────────
        if key in ("cmc", "mv", "manavalue"):
            return self._numeric_query("cmc", op, value, negated)

        # ── Numeric: power / toughness / loyalty ──────────────────────────────
        if key in ("pow", "power"):
            return self._numeric_query("power", op, value, negated, string_field=True)
        if key in ("tou", "toughness"):
            return self._numeric_query("toughness", op, value, negated, string_field=True)
        if key in ("loy", "loyalty"):
            return self._numeric_query("loyalty", op, value, negated, string_field=True)

        # ── Combined power + toughness ────────────────────────────────────────
        if key in ("pt", "powtou"):
            try:
                num = float(value)
            except ValueError:
                return {}
            op_map = {
                ":": "$eq", "=": "$eq",
                "<": "$lt", "<=": "$lte",
                ">": "$gt", ">=": "$gte",
                "!=": "$ne",
            }
            mongo_op = op_map.get(op, "$eq")
            q = {
                "$expr": {
                    mongo_op: [
                        {
                            "$add": [
                                {"$convert": {"input": "$power",     "to": "double", "onError": 0, "onNull": 0}},
                                {"$convert": {"input": "$toughness", "to": "double", "onError": 0, "onNull": 0}},
                            ]
                        },
                        num,
                    ]
                }
            }
            return self._maybe_negate(q, negated)

        # ── Text fields ───────────────────────────────────────────────────────
        if key in ("n", "name"):
            if op == "!":
                # Exact name match (from !"Name" syntax — already emitted by tokenizer)
                q = {"name": {"$regex": f"^{re.escape(value)}$", "$options": "i"}}
                return self._maybe_negate(q, negated)
            return self._text_query("name", value, negated)
        if key in ("o", "oracle", "text"):
            return self._text_query("oracle_text", value, negated)
        if key in ("fo", "fulloracle"):
            return self._text_query("oracle_text", value, negated)
        if key in ("t", "type"):
            return self._text_query("type_line", value, negated)
        if key in ("a", "artist"):
            return self._text_query("artist", value, negated)
        if key in ("ft", "flavor"):
            return self._text_query("flavor_text", value, negated)
        if key in ("wm", "watermark"):
            return self._text_query("watermark", value, negated)

        # ── Exact / enum fields ───────────────────────────────────────────────
        if key in ("e", "s", "set", "edition"):
            return self._exact_query("set", value.lower(), negated)
        if key in ("cn", "number"):
            return self._text_query("collector_number", value, negated)
        if key in ("b", "block"):
            return self._text_query("block_code", value.lower(), negated)
        if key in ("r", "rarity"):
            rmap = {
                "c": "common", "u": "uncommon", "r": "rare",
                "m": "mythic", "mythicrare": "mythic",
                "s": "special", "b": "bonus",
            }
            return self._exact_query("rarity", rmap.get(value.lower(), value.lower()), negated)
        if key in ("l", "lang", "language"):
            return self._exact_query("lang", value.lower(), negated)
        if key == "layout":
            return self._exact_query("layout", value.lower(), negated)
        if key == "border":
            return self._exact_query("border_color", value.lower(), negated)
        if key == "frame":
            # Checks both frame year (e.g. "2015") and frame_effects array
            # (e.g. "showcase", "extendedart", "legendary")
            q = {
                "$or": [
                    {"frame": value.lower()},
                    {"frame_effects": {"$regex": f"^{re.escape(value.lower())}$", "$options": "i"}},
                ]
            }
            return self._maybe_negate(q, negated)
        if key == "stamp":
            return self._exact_query("security_stamp", value.lower(), negated)
        if key in ("st", "set_type"):
            return self._exact_query("set_type", value.lower(), negated)

        # ── Game availability ─────────────────────────────────────────────────
        if key == "game":
            q = {"games": value.lower()}
            return self._maybe_negate(q, negated)

        # ── Format legality ───────────────────────────────────────────────────
        if key in ("f", "format"):
            q = {f"legalities.{value.lower()}": "legal"}
            return self._maybe_negate(q, negated)
        if key == "banned":
            q = {f"legalities.{value.lower()}": "banned"}
            return self._maybe_negate(q, negated)
        if key == "restricted":
            q = {f"legalities.{value.lower()}": "restricted"}
            return self._maybe_negate(q, negated)

        # ── Keywords ──────────────────────────────────────────────────────────
        if key in ("kw", "keyword"):
            return self._text_query("keywords", value, negated)

        # ── Produced mana ─────────────────────────────────────────────────────
        if key in ("produced", "produces"):
            colors = [
                self._COLOR_MAP.get(c, c.upper())
                for c in value.lower()
                if c in self._COLOR_MAP
            ]
            q = {"produced_mana": {"$all": colors}}
            return self._maybe_negate(q, negated)

        # ── Prices ────────────────────────────────────────────────────────────
        if key in ("usd", "eur", "tix"):
            return self._price_query(f"prices.{key}", op, value, negated)
        if key in ("usdfoil", "usd_foil"):
            return self._price_query("prices.usd_foil", op, value, negated)
        if key in ("usdetch", "usd_etched"):
            return self._price_query("prices.usd_etched", op, value, negated)
        if key in ("eurfoil", "eur_foil"):
            return self._price_query("prices.eur_foil", op, value, negated)

        # ── Release date / year ───────────────────────────────────────────────
        if key == "year":
            return self._year_query(op, value, negated)
        if key == "date":
            return self._date_query(op, value, negated)

        # ── is: / has: / not: ─────────────────────────────────────────────────
        if key == "is":
            return self._is_query(value, negated)
        if key == "has":
            return self._is_query(value, negated)
        if key == "not":
            return self._is_query(value, not negated)

        # Generic fallback: treat the key itself as a MongoDB field name and regex-match value
        return self._text_query(key, value, negated)

    # ─── Expression parser (recursive descent: handles AND / OR / NOT / parens) ──

    def _parse_expression(self, tokens: list, pos: int, stop_at_paren: bool = False):
        """
        Parse a sequence of tokens into a MongoDB query dict.
        Implicit operator between adjacent terms is AND.
        OR creates a separate clause group; results are $or-ed.
        Returns (query_dict, new_pos).
        """
        # or_groups: list of AND-clause lists; groups are $or-ed together
        or_groups: list = [[]]
        next_negated = False

        while pos < len(tokens):
            tok = tokens[pos]

            # Close paren — end this level
            if tok["type"] == "PAREN" and tok["value"] == ")":
                if stop_at_paren:
                    pos += 1
                break

            # Open paren — recurse into sub-expression
            if tok["type"] == "PAREN" and tok["value"] == "(":
                sub, pos = self._parse_expression(tokens, pos + 1, stop_at_paren=True)
                if next_negated:
                    sub = {"$nor": [sub]}
                    next_negated = False
                or_groups[-1].append(sub)
                continue

            # Logical operators
            if tok["type"] == "OP":
                if tok["value"] == "OR":
                    or_groups.append([])
                elif tok["value"] == "NOT":
                    next_negated = True
                # AND is default — nothing extra needed
                pos += 1
                continue

            clause = None
            if tok["type"] == "FILTER":
                neg = tok["negated"] or next_negated
                next_negated = False
                clause = self._filter_to_mongo(tok["key"], tok["op"], tok["value"], neg)

            elif tok["type"] == "NAME":
                neg = tok["negated"] or next_negated
                next_negated = False
                # Bare words search name, oracle text, and type line
                clause = self._text_query(
                    ["name", "oracle_text", "type_line"], tok["value"], neg
                )

            if clause:
                or_groups[-1].append(clause)
            pos += 1

        def _and(clauses: list) -> dict:
            if not clauses:
                return {}
            if len(clauses) == 1:
                return clauses[0]
            return {"$and": clauses}

        or_parts = [_and(g) for g in or_groups if g]
        if not or_parts:
            return {}, pos
        if len(or_parts) == 1:
            return or_parts[0], pos
        return {"$or": or_parts}, pos

    def _parse_query(self, query: str) -> dict:
        tokens = self._tokenize(query)
        result, _ = self._parse_expression(tokens, 0)
        return result

    # ─── Main tool ────────────────────────────────────────────────────────────

    def search_scryfall(self, query: str) -> ScryfallSearchResults:
        """
        Searches the local Scryfall card database using Scryfall-like search syntax.

        Supported filters:
          name / n          — name contains text           (e.g. name:bolt, n:"Serra Angel")
          !"name"           — exact name match             (e.g. !"Lightning Bolt")
          o / oracle        — oracle text contains         (e.g. o:flying)
          fo / fulloracle   — oracle text (incl. reminder) (e.g. fo:"first strike")
          t / type          — type line contains           (e.g. t:creature, t:"legendary creature")
          c / color         — color                        (e.g. c:r, c:wub, c>=ub, c=wu)
          id / identity     — color identity               (e.g. id<=wub)
          m / mana          — mana cost symbols            (e.g. mana={W}{U}, mana:{X}, mana={0})
          cmc / mv          — mana value                   (e.g. cmc<=3, mv=2, mv:even, mv:odd)
          pow / power       — power                        (e.g. pow>=4)
          tou / toughness   — toughness                    (e.g. tou<=2)
          pt / powtou       — power + toughness combined   (e.g. pt>=6)
          loy / loyalty     — loyalty                      (e.g. loy>=3)
          e / set           — set code                     (e.g. e:blb, e:m21)
          cn / number       — collector number             (e.g. cn:42)
          b / block         — block code                   (e.g. b:rav)
          r / rarity        — rarity: c u r m s b          (e.g. r:rare, r:m)
          f / format        — format legality              (e.g. f:standard, f:modern)
          banned            — banned in format             (e.g. banned:vintage)
          restricted        — restricted in format         (e.g. restricted:vintage)
          a / artist        — artist name                  (e.g. a:avon)
          ft / flavor       — flavor text                  (e.g. ft:goblin)
          wm / watermark    — watermark text               (e.g. wm:phyrexian)
          is / has          — boolean property             (see list below)
          not               — negated boolean property     (e.g. not:reprint)
          kw / keyword      — rules keyword                (e.g. kw:flying)
          lang              — language code                (e.g. lang:en)
          layout            — card layout                  (e.g. layout:transform)
          border            — border color                 (e.g. border:borderless, border:black)
          frame             — frame year or effect         (e.g. frame:2015, frame:showcase)
          stamp             — security stamp               (e.g. stamp:oval, stamp:acorn)
          st / set_type     — set type                     (e.g. st:expansion, st:commander)
          game              — game availability            (e.g. game:paper, game:arena)
          produced          — produced mana colors         (e.g. produced:g)
          usd / eur / tix   — price comparison             (e.g. usd<=1.00, tix<5)
          usdfoil / eurfoil — foil price comparison        (e.g. usdfoil<=2.00)
          year              — release year                 (e.g. year:2020, year>=2015)
          date              — release date (YYYY-MM-DD)    (e.g. date>=2020-09-25)

        is: / has: / not: properties:
          Card types:   permanent, nonpermanent, spell, historic, party, outlaw, commander
                        legendary, creature, artifact, enchantment, instant, sorcery,
                        planeswalker, land, basic, saga, battle, token
          Creatures:    vanilla, frenchvanilla
          Mana:         hybrid, phyrexian
          Layouts:      split, flip, transform, mdfc, meld, meldpart, meldresult,
                        leveler, dfc, adventure
          Mechanics:    companion, partner
          Color:        multicolored, colorless, monocolored
          Printing:     fullart, foil, nonfoil, etched, textless, oversized, spotlight,
                        reserved, reprint, promo, digital, booster
          has: only:    watermark, indicator

        Color operators:  : / >= (contains), = (exactly), <= (at most), < (proper subset), > (superset)
        Numeric operators: = : < <= > >= !=
        Boolean:  AND  OR  NOT  (also - prefix for negation, e.g. -t:land)
        Grouping: parentheses  ( )
        Bare words search across name, oracle text, and type line.

        :param query: The search query string.
        """
        if not query or not query.strip():
            return "Please provide a search query."

        try:
            mongo_query = self._parse_query(query)
        except Exception as e:
            return f"Query parse error: {e}"

        projection = {
            "_id": 0,
            "name": 1,
            "set": 1,
            "set_name": 1,
            "collector_number": 1,
            "mana_cost": 1,
            "cmc": 1,
            "type_line": 1,
            "oracle_text": 1,
            "power": 1,
            "toughness": 1,
            "loyalty": 1,
            "rarity": 1,
            "colors": 1,
            "color_identity": 1,
            "keywords": 1,
            "legalities": 1,
            "artist": 1,
            "prices": 1,
        }

        try:
            collection = self.client.get_database("scryfall").get_collection("default_cards")
            cursor = collection.find(mongo_query, projection)
            cards = list(cursor)
        except Exception as e:
            return f"Database error: {e}"

        return ScryfallSearchResults(query, len(cards), cards)
