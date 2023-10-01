
<!-- Header -->
<div align="center">
  <h3>ComMod - DEM Community Mod Manager</h3>

  <p>
    Mod manager for Ex Machina/Hard Truck Apocalypse game series.
    <br />
    <a href="https://discord.gg/jZHxYdF"><img src="https://user-images.githubusercontent.com/79088546/174305727-755adfa0-57c2-41b0-9717-8476fcbc4567.png" alt="Discord link"><strong>  Follow the development on Discord »</strong></a>
  </p>
  

  <a href="https://discord.gg/jZHxYdF">
  <img src="https://user-images.githubusercontent.com/79088546/174285554-cf467b80-7264-475f-94ec-bacc204b04c9.png" alt="Logo" width="400">
  </a>

  <a href="https://github.com/DeusExMachinaTeam/EM-CommunityPatch"><img src="https://user-images.githubusercontent.com/79088546/174311991-c20e04bb-1cad-44e2-a0e9-5984de6d8d55.png"> Part of Community Remaster project</a>
</div>

<!-- About the project -->

**ComMod** is a mod manager and installer that allows you to apply binary patches to game files necessary for [Community Remaster](https://github.com/DeusExMachinaTeam/EM-CommunityPatch) and complex mods based on it, e.g. [Improved Storyline](https://github.com/zatinu322/ImprovedStoryline/).

* Shows the user information about the mod (description, screenshots, list of changes, links from the author, etc.)
* Streamlines installation of mods, allowing user to choose which optional content to install
* Multiple versions of the same mod are conveniently shown as a single entity in Library
* Managing multiple game copies and launching the game in different modes is easy from Launcher app page

Distributing mod as ComMod package gives modders support for:
* A choice of binary patches which can be easily enabled or disabled via mod manifest
* Packaging of different mod versions and localisations as a single archive, reusing common files between versions
* Support not only for an optional content but different mutually exclusive 'variants' of the same option, reducing the chances of user error and incorrect installation
* Setting up compatibility rules (name, version, the presence of optional content) with other mods for the game
* All installed mods are tracked and create fingerprint file which helpes to track user configuration in case of errors and need for support

## Demonstation
![Community Remaster installation][patcher_tutorial]
*Installing Community Remaster with ComMod - Russian localisation shown*

<p align="right">(<a href="#top">to the top</a>)</p>

## Making mods compatible
Making a mod compatible with ComMod is easy - just place the files in the zip or 7z  archive as specified in the documentation with a special manifest.yaml file, describing to ComMod how the mod should be displayed to the user and how it should be installed.

Packing the mod in an archive with the ComMod manifest is the preferred way to distribute mods for ComPatch and ComRemaster.

ComMod also allows the installation of old mods that were developed for the clean version of the game. When installing them via ComMod, a minimal set of edits will be applied to the game exe to fix common game crashes ("ComPatch Mini"). These mod will need a simple manifest added to work with ComMod.

ComMod is translated into English, Russian and Ukrainian.


</br>
&#x1F53B; Important! &#x1F53B;
<ol>
<b>commod.exe</b> - installer and mod manager, that may cause false positives of antiviruses.
In the installation process, the program patches the original exe of the game byte by byte, copies the patch\remaster files in the correct order, and edits certain game files. Unfortunately, both the specifics of the work (editing another exe) and the fact that the installer is written in Python means that you may need to add the file to your antivirus exceptions. We apologize for any inconvenience, the file does not contain any viruses.
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
Project license is loosely based on MIT license but forbidding commerical usage and adding an additional clause about specifics of attribution in case of redistribution of the code.

<br />
For details, please see the full license in the LICENSE file.
</ol>
</details>
<br />
