
<!-- Header -->
<div align="center">
  <h3>ComMod - DEM Community Mod Manager</h3>

  <p>
    Mod manager for Ex Machina/Hard Truck Apocalypse game series.
    <br />
  </p>
  

  <a href="https://discord.gg/jZHxYdF">
  <img src="https://user-images.githubusercontent.com/79088546/174285554-cf467b80-7264-475f-94ec-bacc204b04c9.png" alt="Logo" width="400">
  </a>

  <a href="https://github.com/DeusExMachinaTeam/EM-CommunityPatch/blob/main/README_EN.md"><img src="https://user-images.githubusercontent.com/79088546/174311991-c20e04bb-1cad-44e2-a0e9-5984de6d8d55.png"><strong> Part of Community Remaster project »</strong></a>

  <a href="https://discord.gg/jZHxYdF"><img src="https://user-images.githubusercontent.com/79088546/174305727-755adfa0-57c2-41b0-9717-8476fcbc4567.png" alt="Discord link">  Follow the development on Discord »</a>
<br />
<br />
</div>

<!-- About the project -->

**ComMod** is a mod manager that acts as an installer for [Community Remaster](https://github.com/DeusExMachinaTeam/EM-CommunityPatch) and any complex mods based on it, e.g. [Improved Storyline](https://github.com/zatinu322/ImprovedStoryline/).

Comparing the user experience to manual installation of mods, ComMod can:
* Show the user information about the mod (description, screenshots, formatted list of changes, links from the author, etc.)
* Streamline installation of mods, allowing user to choose which optional content to install all from a slick GUI
* Display multiple versions of the same mod as a single entity in Library, keeping user's mod collection tidy and easily accessible
* Manage multiple game copies and launch the game in different modes from Launcher app page

Distributing mod as ComMod package gives modders support for:
* A choice of binary patches created as part of ComRemaster project, which can be easily enabled or disabled via mod manifest
* Packaging of different mod versions and localisations as a single archive, reusing common files between versions
* Setting up compatibility rules (name, version, the presence of optional content) with other mods for the game
* Mods can include not only an optional content but different mutually exclusive 'variants' of the same option, reducing the chances of user error and incorrect installation. Adding localisations and compatibility patches for different mods is also supported
* All installed mods are tracked and create 'fingerprint' file which helpes to track user configuration in case of errors and need for support

ComMod also includes super lightweight news section synced from web to notify users of new releases in their language, and the next major release is planned to add an option to download mods straight from the mod manager, reusing same pretty UI used to display mods added to library.

## Running ComMod
Install dependencies to your venv:
```sh
> pip install -r ./requirements.txt
```

Run entry point from:
```sh
> py ./src/commod.py
```

## Demonstration
![Community Remaster installation][patcher_tutorial]
*Installing Community Remaster with ComMod - Russian localisation shown*

<p align="right">(<a href="#top">to the top</a>)</p>

## Making mods compatible
Making a mod compatible with ComMod is easy - just place the files in the zip or 7z  archive as specified in the documentation with a special manifest.yaml file, describing to ComMod how the mod should be displayed to the user and how it should be installed. Documentation is currently available in [Russian](https://deuswiki.com/w/ComMod) or [machine translated English](https://deuswiki-com.translate.goog/w/ComMod?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en-US&_x_tr_pto=wapp). Don't hesitate to ask on [our Discord](https://discord.gg/jZHxYdF) if you have any questions or suggestions.

Packing the mod in an archive with the ComMod manifest is the preferred way to distribute mods for ComPatch and ComRemaster.

ComMod also allows the installation of old mods that were developed for the clean version of the game. When installing them via ComMod, a minimal set of edits will be applied to the game exe to fix common game crashes ("ComPatch Mini"). These mod will need a simple manifest added to work with ComMod.

ComMod is translated into English, Russian and Ukrainian.


</br>
&#x1F53B; Important! &#x1F53B;
<ol>
<b>commod.exe</b> binary may cause false positives of antiviruses.
In the installation process, the program applies binary patches the original exe and dll files of the game, copies the patch\remaster files in the correct order, and edits certain game resource files. Unfortunately, both the specifics of the work (patching another executable) and the fact that the installer is written in Python means that you may need to add the file to your antivirus exceptions. We apologize for any inconvenience, the binaries distributed on this Github does not contain any viruses but you are welcome to review code and recompile app youself.
</ol>

<p align="right">(<a href="#top">to the top</a>)</p>

<!-- Screenshot shortcuts -->
[discord_logo_sml]: https://user-images.githubusercontent.com/79088546/174304599-33630ab1-e5ce-4410-a720-55046783d085.png

[dem_logo_sml]: https://user-images.githubusercontent.com/79088546/174311991-c20e04bb-1cad-44e2-a0e9-5984de6d8d55.png

[patcher_tutorial]: https://user-images.githubusercontent.com/79088546/246537517-5e8cb714-960c-4576-8722-498b6bba8b11.gif


## Licensing:
<details>
<summary>License information</summary>
<ol>
Project's license is loosely based on MIT license but forbidding commercial usage and adding an additional clause about details of required attribution for derivative works.

<br />
For details, please see the full license in the LICENSE file.
</ol>
</details>
<br />
