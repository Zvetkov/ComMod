#!/bin/bash

venvpath="venv_313_linux"
pyversion="python3.13"

. ${venvpath}/bin/activate

python -m nuitka --onefile \
  --include-data-dir=./src/commod/assets=commod/assets \
  --include-data-dir=./src/commod/localisation=commod/localisation \
  --include-data-dir="./venv_313_linux/lib/python3.13/site-packages/flet_desktop/app/=flet_desktop/app/" \
  --file-version=3.0.4 \
  --file-description="Deus Ex Machina Community Mod Manager" \
  ./src/commod_launcher.py

#   --include-data-file="./${venvpath}/lib/${pyversion}/site-packages/flet_desktop/app/flet/*=flet_desktop/app/flet/" \
#   --include-data-file="./${venvpath}/lib/${pyversion}/site-packages/flet_desktop/app/flet/data/*=flet_desktop/app/flet/data/" \