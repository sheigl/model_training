#!/bin/sh
# Shared named-argument parsing for the run_<slug>.sh wrappers (Story 049).
#
# All model/count slots are named flags (or overridable DEFAULT_* variables),
# so argument order never matters:
#
#   run_combos.sh --count 1000 --model M --validation-model V --validation-pct 1 \
#                 --dry-run --observer-model OBS --shadow-validation-model SHADOW
#
# A lone leading integer still works as the legacy count shorthand:
#   run_combos.sh 1000

# Per-script defaults are set by the sourcing run_<slug>.sh via
# DEFAULT_MODEL / DEFAULT_VALIDATION_MODEL (the environment can override
# them before invoking the script). Everything else defaults to off.

parse_generator_args() {
  NUM=""
  MODEL=""
  VALIDATION_MODEL=""
  VALIDATION_PCT=1
  DRY_RUN=""
  OBSERVER_MODEL=""
  SHADOW_VALIDATION_MODEL=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --count)                    NUM="$2";                              shift 2 ;;
      --model)                    MODEL="$2";                            shift 2 ;;
      --validation-model)         VALIDATION_MODEL="$2";                 shift 2 ;;
      --validation-pct)           VALIDATION_PCT="$2";                   shift 2 ;;
      --dry-run)                  DRY_RUN="--dry-run";                   shift ;;
      --observer-model)           OBSERVER_MODEL="$2";                   shift 2 ;;
      --shadow-validation-model)  SHADOW_VALIDATION_MODEL="$2";          shift 2 ;;
      *)                          NUM="${1:-$NUM}";                      shift ;;
    esac
  done
  NUM="${NUM:-1}"
  MODEL="${MODEL:-$DEFAULT_MODEL}"
  VALIDATION_MODEL="${VALIDATION_MODEL:-$DEFAULT_VALIDATION_MODEL}"
}
