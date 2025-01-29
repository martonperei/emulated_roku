# emulated_roku

This library is for emulating the Roku API. Discovery is tested with Logitech Harmony and Android remotes.
Only key press / down / up events and app launches (10 dummy apps) are implemented in the RokuCommandHandler callback.  
Other functionality such as input, search will not work.
See the [example](example.py) on how to use.

Application list can be customized with a string in this format :

`1:first-app,2:second-app,3:third-app`

Which would generate this response :

```angular2html
<apps>
    <app id="1" version="1.0.0">first-app</app>
    <app id="2" version="1.0.0">second-app</app>
    <app id="3" version="1.0.0">third-app</app>
</apps>
```