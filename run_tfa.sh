#!/bin/bash
export PYTHONUTF8=1
DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "================================================================"
echo "  Thawing Field Analyzer"
echo "================================================================"
echo "  Settings: tfa-environment-settings.json"
echo "  Results : results/"
echo "================================================================"
echo ""

mkdir -p "$DIR/results"
cd "$DIR/.."
python "$DIR/run_tfa.py"
TFA_EXIT=$?

echo ""
echo "================================================================"
if [ "$TFA_EXIT" -eq 0 ]; then
  echo "  Run complete."
else
  echo "  Run failed."
fi
echo "================================================================"
echo ""
exit "$TFA_EXIT"
