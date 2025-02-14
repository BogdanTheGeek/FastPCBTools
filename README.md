# Fast PCB Tools
A collection of tools, useful for manufacturing PCBs at home.

## Tools
All of the Gerber/Excellon files tested have been from KiCAD.
The G-Code produce should be pretty portable, but its mostly targeted for LinuxCNC and grbl.

### Edge Router
```sh
> ./edge_router.py -h
usage: edge_router.py [-h] [-i INPUT] [-o OUTPUT] [-r RETRACT] [-s START] [-e END] [-t TOOL]
                      [-x ENTRY ENTRY] [-f FEED]

Gerber file parser

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Input file path
  -o OUTPUT, --output OUTPUT
                        Output file path
  -r RETRACT, --retract RETRACT
                        Retract height
  -s START, --start START
                        Cut start height
  -e END, --end END     Cut end height
  -t TOOL, --tool TOOL  Tool diameter
  -x ENTRY ENTRY, --entry ENTRY ENTRY
                        Entry point
  -f FEED, --feed FEED  Feedrate in mm/min
```
Convert board edge Gerber file (Kicad, metric) into machining G-Code. Supports nested pockets. Does not support intersecting polygons or incomplete loops.

### Drill
```sh
> ./drill.py -h
usage: drill.py [-h] [-i INPUT] [-o OUTPUT] [-r RETRACT] [-s START] [-e END] [-x ENTRY ENTRY]
                [-f FEED]

Gerber file parser

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Input file path
  -o OUTPUT, --output OUTPUT
                        Output file path
  -r RETRACT, --retract RETRACT
                        Retract height
  -s START, --start START
                        Cut start height
  -e END, --end END     Cut end height
  -x ENTRY ENTRY, --entry ENTRY ENTRY
                        Entry point
  -f FEED, --feed FEED  Feedrate in mm/min
```
Converts `.drl` file into G-Code drilling and routing commands. Also, optimises the order of the drilling and includes tool swapping.

## More
 - [photonic-etcher](https://github.com/Andrew-Dickinson/photonic-etcher) - Convert Gerbers to SLA 3D printer compatible files for etching.
 - [cginc](https://github.com/BogdanTheGeek/cginc) - G-Code Visualiser
