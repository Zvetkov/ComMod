$venvpath = "venv"

. $venvpath\Scripts\activate.ps1


python -m nuitka --onefile --include-data-dir=.\src\commod\assets=commod\assets --include-data-dir=.\src\commod\localisation=commod\localisation --include-data-dir=".\$venvpath\Lib\site-packages\flet\bin\=flet\bin\" --include-data-file=".\$venvpath\Lib\site-packages\flet\bin\flet\*.dll=flet\bin\flet\" --include-data-file=".\$venvpath\Lib\site-packages\flet\bin\flet\*.exe=flet\bin\flet\" --include-data-file=".\$venvpath\Lib\site-packages\flet\bin\flet\data\*.so=flet\bin\flet\data\" --windows-icon-from-ico=".\assets\icon.ico" --windows-company-name="DEM" --windows-product-name="ComMod" --windows-file-version=2.1.0 --windows-file-description="Deus Ex Machina Community Mod Manager" --onefile-windows-splash-screen-image=.\assets\logo_trasparent_bg.png .\src\commod.py
