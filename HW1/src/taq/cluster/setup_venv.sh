#!/usr/bin/env bash
# One-shot venv bootstrap for Engaging (MIT ORCD).
#
# Base miniforge Python 3.12 is fine but pyarrow is missing. We build a small
# project-local venv with just what the TAQ pipeline needs.
#
# Run once from ~/Fin_Tech/HW1 on the cluster login node:
#     bash src/taq/cluster/setup_venv.sh
#
# After this, every subsequent job activates the venv rather than rebuilding.

set -euo pipefail

# Root is the project dir on the cluster (always called from there).
ROOT="${HOME}/Fin_Tech/HW1"
cd "${ROOT}"

# Ensure the default miniforge module is loaded.
module load miniforge/25.11.0-0 2>/dev/null || true

if [[ -d "venv" ]]; then
    echo "[setup_venv] venv/ already exists; skipping creation."
else
    echo "[setup_venv] creating venv/ ..."
    python3 -m venv venv
fi

# shellcheck source=/dev/null
source venv/bin/activate

echo "[setup_venv] upgrading pip + installing deps ..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet \
    "numpy>=2.0" \
    "pandas>=2.2" \
    "pyarrow>=17" \
    "scipy>=1.14"

echo
echo "[setup_venv] OK. Package versions:"
python -c "import pandas, pyarrow, numpy, scipy; \
print(f'  pandas  {pandas.__version__}'); \
print(f'  pyarrow {pyarrow.__version__}'); \
print(f'  numpy   {numpy.__version__}'); \
print(f'  scipy   {scipy.__version__}')"
