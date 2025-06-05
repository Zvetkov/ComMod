$venvpath = "venv313"

. $venvpath\Scripts\activate.ps1


python -m nuitka --onefile --include-data-dir=.\src\commod\assets=commod\assets --include-data-dir=.\src\commod\localisation=commod\localisation --include-data-dir=".\$venvpath\Lib\site-packages\flet_desktop\app\=flet_desktop\app\" --include-data-file=".\$venvpath\Lib\site-packages\flet_desktop\app\flet\*.dll=flet_desktop\app\flet\" --include-data-file=".\$venvpath\Lib\site-packages\flet_desktop\app\flet\*.exe=flet_desktop\app\flet\" --include-data-file=".\$venvpath\Lib\site-packages\flet_desktop\app\flet\data\*.so=flet_desktop\app\flet\data\" --windows-icon-from-ico=".\assets\icon.ico" --windows-company-name="DEM" --windows-product-name="ComMod" --windows-file-version=3.0.4 --windows-file-description="Deus Ex Machina Community Mod Manager" --windows-console-mode=force .\src\commod_launcher.py

# --onefile-windows-splash-screen-image=.\assets\logo_trasparent_bg.png