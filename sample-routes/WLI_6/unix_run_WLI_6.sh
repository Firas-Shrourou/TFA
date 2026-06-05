#!/bin/bash
export PYTHONUTF8=1
DIR="$(dirname "$0")"

echo ""
echo "================================================================"
echo "  Thawing Field Analyzer | WLI_6 Sample Run"
echo "================================================================"
echo "  This script runs the WLI_6 benchmark route."
echo ""
echo "  The tfa-environment-settings.json in this folder is"
echo "  pre-configured for WLI_6:"
echo "    Potential  : WLI  (Peebles & Vilenkin 1999)"
echo "    Parameters : alpha = 2.0 |  phi_inf = 1.35"
echo "    Initial    : phi_i = 1.35,  phi_N_i = 0.0"
echo ""
echo "  Results will be written to the results/ subfolder."
echo "================================================================"
echo ""

python "$DIR/run_WLI_6.py"

echo ""
echo "================================================================"
echo "  WLI_6 run complete."
echo "  Open the results/ subfolder to inspect outputs."
echo "================================================================"
echo ""

read -p "Press Enter to continue..."
