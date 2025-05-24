#!/usr/bin/env python

import argparse
import datetime
import sys


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __str__(self):
        return f"({self.x}, {self.y})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)

    def dist(self, other):
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5

    def __lt__(self, other):
        return False

    def __hash__(self):
        return hash((self.x, self.y))


def parse_number(number: str):
    if number == "":
        return 0
    return float(number)


def parse_command(line: str):
    command = {}
    last_point = "?"
    for ch in line:
        if ch.isalpha():
            last_point = ch
            command[ch] = ""
        else:
            command[last_point] += ch
    coord = {}
    for key in command:
        if key in ["X", "Y", "I", "J"]:
            coord[key] = parse_number(command[key])

    p = Point(coord.get("X", 0), coord.get("Y", 0))
    code = "G" + command.get("G", "00")  # default to travel

    return {code: p}


def parse_drl(file_path: str):
    drill_mode = False
    tools = {}
    selected_tool = None
    with open(file_path, "r") as file:
        line_no = 0
        for line in file:
            line_no += 1
            try:
                line = line.split(";")[0].strip()
                if len(line) == 0:
                    continue
                if line.startswith("T"):
                    if "C" in line:
                        params = line.split("C")
                        t = int(params[0][1:])
                        tools[t] = {
                            "diameter": float(params[1]),
                            "points": [],
                            "paths": [],
                        }
                    else:
                        selected_tool = int(line[1:])
                    continue
                if line.startswith("G05"):
                    drill_mode = True
                    continue
                if line.startswith("M15"):
                    # Plunge
                    tools[selected_tool]["paths"].append({"M15": ""})
                    continue
                if line.startswith("M16"):
                    # Retract
                    tools[selected_tool]["paths"].append({"M16": ""})
                    continue
                if line.startswith(("G00", "G01")):
                    drill_mode = False
                    parsed = parse_command(line)
                    tools[selected_tool]["paths"].append(parsed)
                    continue
                if line.startswith(("X", "Y")) and drill_mode:
                    _, p = parse_command(line).popitem()
                    tools[selected_tool]["points"].append(p)
                    continue
            except Exception as e:
                print(f"Error parsing line({line_no}): {line}")
                print(e)
                raise e
    return tools


def sort_points(points: list, entry: Point):
    if len(points) == 0:
        return []
    sorted_points = []
    points = points.copy()
    current = entry
    while len(points) > 0:
        next_point = min(points, key=lambda p: current.dist(p))
        sorted_points.append(next_point)
        points.remove(next_point)
        current = next_point
    return sorted_points


def tool_change(t: int, d: float):
    return f"T{t} M06; {d}mm\n"


def generate_drill_gcode(p: Point, args):
    output = f"G00 X{p.x} Y{p.y}\n"
    output += f"G00 Z{args.start}\n"
    output += f"G01 Z{args.end}\n"
    output += f"G00 Z{args.retract}\n"
    return output


def generate_bore_gcode(p: Point, args, diameter: float, floor=False):
    path_r = (diameter - args.max_tool / 2) / 2
    offset = path_r + args.max_tool / 2
    pitch = args.bore_pitch

    output = f"G00 X{p.x - offset} Y{p.y}\n"
    output += f"G00 Z{args.start}\n"

    output += "G91; Switch to relative positioning\n"
    remaining = args.start - args.end
    while remaining - pitch > 0:
        output += f"G3 Z{-pitch} I{path_r}\n"
        remaining -= pitch
    output += f"G3 Z{-remaining} I{path_r}\n"
    output += "G90; Switch back to absolute positioning\n"

    if floor:
        output += f"G3 I{path_r}\n"
    output += f"G00 Z{args.retract}\n"
    return output


def generate_gcode(tools, args, file_path=None, bore=False):
    output = f"""; Generated on {datetime.datetime.now()}
; Command: `{" ".join(sys.argv)}`
G21; Set units to mm
G90; Set absolute positioning
G17; Set XY plane
G94; Set feedrate to mm/min
G40; Disable tool radius compensation
G49; Disable tool length offset
G01 F{args.feed}; Set feedrate to {args.feed} mm/min
M03 S{args.rpm}; Start spindle at {args.rpm} RPM
"""

    output += f"G00 Z{args.retract}\n"

    for t, tool in tools.items():
        output += tool_change(t, tool["diameter"])
        for p in tool["points"]:
            if bore:
                output += generate_bore_gcode(p, args, tool["diameter"])
            else:
                output += generate_drill_gcode(p, args)

        for path in tool["paths"]:
            for code in path:
                if code == "M15":
                    output += f"G00 Z{args.start}\n"
                    output += f"G01 Z{args.end}\n"
                elif code == "M16":
                    output += f"G00 Z{args.retract}\n"
                else:
                    output += f"{code} X{path[code].x} Y{path[code].y}\n"

    output += "M5; Stop spindle\n"
    output += "M30; End of program\n"
    file_path = file_path or args.output
    with open(file_path, "w") as file:
        file.write(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert a drill file to GCode")
    parser.add_argument("-i", "--input", help="Input file path")
    parser.add_argument("-o", "--output", help="Output file path", default=None)
    parser.add_argument(
        "-r", "--retract", type=float, default=20.0, help="Retract height"
    )
    parser.add_argument(
        "-s", "--start", type=float, default=1.0, help="Cut start height"
    )
    parser.add_argument("-e", "--end", type=float, default=-1.65, help="Cut end height")
    parser.add_argument(
        "-x", "--entry", type=float, nargs=2, default=(0, 0), help="Entry point"
    )
    parser.add_argument(
        "-f", "--feed", type=float, default=100.0, help="Feedrate in mm/min"
    )
    parser.add_argument(
        "-rpm", "--rpm", type=float, default=10000.0, help="Spindle speed in RPM"
    )
    parser.add_argument(
        "-bp", "--bore-pitch", type=float, default=0.5, help="Bore pitch in mm"
    )
    parser.add_argument(
        "-mt",
        "--max-tool",
        type=float,
        default=1.5,
        help="Max tool diameter in mm, Everything above this will be bored",
    )
    parser.add_argument(
        "-sp",
        "--split",
        type=bool,
        default=True,
        help="Split each tool into its own file",
    )
    args = parser.parse_args()

    if not args.output:
        args.output = ".".join(args.input.split(".")[0:-1]) + ".nc"
        print(f"Output file not specified, using `{args.output}`")

    tools = parse_drl(args.input)
    for tool in tools:
        print(f"Tool: {tool}")
        print(f"Diameter: {tools[tool]['diameter']}")
        print(f"Points({len(tools[tool]['points'])}): {tools[tool]['points']}")
        print(f"Paths({len(tools[tool]['paths'])}): {tools[tool]['paths']}")

    # merge tools with the same diameter
    merged_tools = {}
    for tool in tools:
        diameter = tools[tool]["diameter"]
        if diameter not in merged_tools:
            merged_tools[diameter] = {"points": [], "paths": [], "diameter": diameter}
        merged_tools[diameter]["points"].extend(tools[tool]["points"])
        merged_tools[diameter]["paths"].extend(tools[tool]["paths"])

    # replace diameter with tool number
    tools = {}
    for i, diameter in enumerate(merged_tools):
        tools[i + 1] = merged_tools[diameter]
        tools[i + 1]["diameter"] = diameter

    # sort points
    for tool in tools:
        tools[tool]["points"] = sort_points(tools[tool]["points"], Point(*args.entry))

    if args.split:
        path = args.output.split(".")
        suffix = path[-1]
        file_path = ".".join(path[0:-1])

        ops = []
        for tool in tools:
            ops.append((tool, tools[tool]["diameter"] > args.max_tool))

        for tool, bore in ops:
            d = tools[tool]["diameter"]
            generate_gcode(
                {tool: tools[tool]},
                args,
                f"{file_path}_T{tool}({d}mm).{suffix}",
                bore=bore,
            )
    else:
        generate_gcode(tools, args, args.output)
