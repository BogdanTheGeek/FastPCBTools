#!/usr/bin/env python

import argparse
from shapely.geometry import Polygon
import numpy as np
import cmath
import sys
import datetime


FMT = (4, 6)
UNIT = "mm"

TOLERANCE = 1 / (2**6)  # 1/64 mm


class Within:
    def __init__(self, o):
        self.o = o

    def __lt__(self, other):
        return self.o.within(other.o)


def parse_number(coordinate: str):
    return float(coordinate) / 10 ** FMT[1]


def parse_command(code: str, line: str):
    command = {"code": code}
    last_point = "?"
    for ch in line:
        if ch.isalpha():
            last_point = ch
            command[ch] = ""
        else:
            command[last_point] += ch
    for key in command:
        if key in ["X", "Y", "I", "J"]:
            command[key] = parse_number(command[key])
    return command


def parse_gerber(file_path: str):
    commands = []
    with open(file_path, "r") as file:
        last_command = None
        for line in file:
            line = line.strip()[0:-1]
            if line.startswith("%"):
                continue
            if line.startswith("G04 Gerber"):
                # G04 Gerber Fmt 4.6, Leading zero omitted, Abs format (unit mm)*
                options = line.split(", ")
                for option in options:
                    if "Fmt" in option:
                        FMT = tuple(map(int, option.split(" ")[-1].split(".")))
                        print(f"Setting FMT to {FMT}")
                    if "unit" in option:
                        UNIT = option.split(" ")[-1][0:-1]
                        print(f"Setting UNIT to {UNIT}")
                continue
            if line.startswith("G04"):
                continue
            if line.startswith("G"):
                last_command = line
                continue
            if line.startswith("X"):
                assert last_command is not None
                parsed = parse_command(last_command, line)
                commands.append(parsed)
                continue
    return commands


class Point:
    def __init__(self, x, y):
        if TOLERANCE > 0:
            x = round(x / TOLERANCE) * TOLERANCE
            y = round(y / TOLERANCE) * TOLERANCE

        self.x = x
        self.y = y

    def __str__(self):
        return f"({self.x}, {self.y})"

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)


class Line:
    def __init__(self, start: Point, end: Point):
        self.start = start
        self.end = end

    def __str__(self):
        return f"Line({self.start}, {self.end})"


class Arc:
    def __init__(self, start: Point, end: Point, center: Point, clockwise: bool):
        self.start = start
        self.end = end
        self.center = center
        self.clockwise = clockwise

    def __str__(self):
        return f"Arc{self.start}, {self.end}, {self.center}, {self.clockwise})"


def extract_edges(commands):
    edges = []
    cutting = False
    current_p = Point(0, 0)
    for edge in commands:
        assert "X" in edge
        assert "Y" in edge
        assert "D" in edge

        if edge["D"] == "01":
            cutting = True
        elif edge["D"] == "02":
            cutting = False
        else:
            raise ValueError(f"Unknown command {edge['D']}")

        if not cutting:
            current_p = Point(edge["X"], edge["Y"])
            continue

        start_p = current_p
        current_p = Point(edge["X"], edge["Y"])

        if edge["code"] == "G01":
            edges.append(Line(start_p, current_p))
        elif edge["code"] == "G02":
            edges.append(
                Arc(start_p, current_p, start_p + Point(edge["I"], edge["J"]), True)
            )
        elif edge["code"] == "G03":
            edges.append(
                Arc(start_p, current_p, start_p + Point(edge["I"], edge["J"]), False)
            )
        else:
            raise ValueError(f"Unknown command {edge['code']}")
    return edges


def create_path(edges):
    linked_edges = [edges[0]]
    unlinked_edges = edges[1:]
    last_remaining_edges = 0
    while last_remaining_edges != len(unlinked_edges):
        last_remaining_edges = len(unlinked_edges)
        for edge in unlinked_edges:
            if linked_edges[-1].end == edge.start:
                print(f"Appending edge {edge} to the end of path")
                linked_edges.append(edge)
                unlinked_edges.remove(edge)
                continue
            if linked_edges[0].start == edge.end:
                print(f"Prepending edge {edge} to the start of path")
                linked_edges.insert(0, edge)
                unlinked_edges.remove(edge)
                continue
            if linked_edges[0].start == edge.start:
                print(f"Reversing edge {edge} and prepending to the start of path")
                if isinstance(edge, Line):
                    linked_edges.insert(0, Line(edge.end, edge.start))
                else:
                    linked_edges.insert(
                        0, Arc(edge.end, edge.start, edge.center, not edge.clockwise)
                    )
                unlinked_edges.remove(edge)
                continue
            if linked_edges[-1].end == edge.end:
                print(f"Reversing edge {edge} and appending to the end of path")
                if isinstance(edge, Line):
                    linked_edges.append(Line(edge.end, edge.start))
                else:
                    linked_edges.append(
                        Arc(edge.end, edge.start, edge.center, not edge.clockwise)
                    )
                unlinked_edges.remove(edge)
                continue
            print(f"Edge {edge} is not connected to the path")

    if linked_edges[0].start != linked_edges[-1].end:
        print("Warning: path is not closed")
        input("Press Enter to continue...")

    return linked_edges, unlinked_edges


def path_to_polygon(edges):
    points = [edge.start for edge in edges] + [edges[-1].end]
    return Polygon([(p.x, p.y) for p in points])


def polygon_to_path(polygon):
    exterior_coords = list(polygon.exterior.coords)
    edges = []
    for i in range(len(exterior_coords) - 1):
        p1 = exterior_coords[i]
        p2 = exterior_coords[i + 1]
        edges.append(Line(Point(*p1), Point(*p2)))
    return edges


def offset_polygon(polygon, distance: float):
    # Offset the polygon using Shapely's buffer method
    offset_polygon = polygon.buffer(distance, resolution=16)

    if not offset_polygon.is_valid or offset_polygon.is_empty:
        raise ValueError("Offset too large, path disappears")
    return offset_polygon


def offset_path(edges, distance: float):
    """
    Offsets a closed path inward or outward.

    :param edges: List of svgpathtools Path segment objects (Line, Arc)
    :param distance: Positive for outward, negative for inward
    :return: List of offset Path segments
    """
    # Convert edges to Shapely polygon
    polygon = path_to_polygon(edges)

    # Offset the polygon
    offset = offset_polygon(polygon, distance)

    # Convert offset polygon back to path
    offset_edges = polygon_to_path(offset)

    return offset_edges


def approximate_arc(arc, num_segments=20):
    """
    Approximate an Arc with a series of Line segments.

    :param arc: svgpathtools.Arc object
    :param num_segments: Number of line segments to approximate the arc
    :return: List of svgpathtools.Line objects
    """
    points = []

    start = complex(arc.start.x, arc.start.y)
    end = complex(arc.end.x, arc.end.y)
    center = complex(arc.center.x, arc.center.y)

    # Compute the radius
    radius = abs(center - start)

    # Convert start/end points to angles relative to the center
    start_angle = np.angle(start - center)
    end_angle = np.angle(end - center)

    # Ensure correct sweep direction
    if not arc.clockwise:
        if end_angle < start_angle:
            end_angle += 2 * np.pi
    else:
        if end_angle > start_angle:
            end_angle -= 2 * np.pi

    print(f"Approximating arc from {start_angle} to {end_angle}")

    # Generate points along the arc
    angles = np.linspace(start_angle, end_angle, num_segments)
    for angle in angles:
        point = center + radius * cmath.exp(1j * angle)
        points.append(Point(point.real, point.imag))

    # Convert points to line segments
    lines = [Line(points[i], points[i + 1]) for i in range(len(points) - 1)]
    return lines


def segment_path(edges):
    new_edges = []
    for edge in edges:
        if isinstance(edge, Line):
            new_edges.append(edge)
        elif isinstance(edge, Arc):
            new_edges += approximate_arc(edge)
    return new_edges


def find_closest_edge(edges: list, point: Point) -> int:
    closest_i = None
    closest_dist = float("inf")
    for i in range(len(edges)):
        edge = edges[i]
        dist = abs(complex(edge.start.x, edge.start.y) - complex(point.x, point.y))
        if dist < closest_dist:
            closest_i = i
            closest_dist = dist
    assert closest_i is not None
    return closest_i


def reorder_edges(edges: list, start: int) -> list:
    return edges[start:] + edges[:start]


def generate_header(args):
    return f"""; Generated on {datetime.datetime.now()}
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


def generate_footer(args):
    return """M05; Stop spindle
M30; End of program"""


def generate_route_gcode(edges, args):
    output = f"G00 Z{args.retract};\n"
    output += f"G00 X{edges[0].start.x} Y{edges[0].start.y};\n"
    output += f"G00 Z{args.start};\nG01 Z{args.end};\n"

    for edge in edges:
        if isinstance(edge, Line):
            output += f"G01 X{edge.end.x} Y{edge.end.y};\n"
        elif isinstance(edge, Arc) and edge.clockwise:
            center_offset = edge.center - edge.start
            output += f"G02 X{edge.end.x} Y{edge.end.y} I{center_offset.x} J{center_offset.y};\n"
        elif isinstance(edge, Arc) and not edge.clockwise:
            center_offset = edge.center - edge.start
            output += f"G03 X{edge.end.x} Y{edge.end.y} I{center_offset.x} J{center_offset.y};\n"
        else:
            raise ValueError(f"Unknown edge type {edge}")

    output += f"G00 Z{args.retract};\n"
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create Routing Job GCode from Board Edge Gerber"
    )
    parser.add_argument("-i", "--input", help="Input file path")
    parser.add_argument("-o", "--output", help="Output file path", default=None)
    parser.add_argument(
        "-r", "--retract", type=float, default=20.0, help="Retract height"
    )
    parser.add_argument(
        "-s", "--start", type=float, default=1.0, help="Cut start height"
    )
    parser.add_argument("-e", "--end", type=float, default=-1.65, help="Cut end height")
    parser.add_argument("-t", "--tool", type=float, default=2.0, help="Tool diameter")
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
        "--tolerance", type=float, default=TOLERANCE, help="Tolerance for path joining"
    )
    args = parser.parse_args()
    TOLERANCE = args.tolerance

    if not args.output:
        args.output = ".".join(args.input.split(".")[0:-1]) + ".nc"
        print(f"Output file not specified, using `{args.output}`")

    commands = parse_gerber(args.input)
    edges = extract_edges(commands)

    paths = []
    path, unlinked_edges = create_path(edges)
    paths.append(path)
    last_remaining_edges = 0
    while len(unlinked_edges) > 0 and len(unlinked_edges) != last_remaining_edges:
        last_remaining_edges = len(unlinked_edges)
        path, unlinked_edges = create_path(unlinked_edges)
        paths.append(path)

    entry = Point(*args.entry)

    output = generate_header(args)

    polygons = []

    for i, edges in enumerate(paths):
        closest_edge = find_closest_edge(edges, entry)

        edges = reorder_edges(edges, closest_edge)
        edges = segment_path(edges)

        polygon = path_to_polygon(edges)
        polygons.append(polygon)

    sorted_polygons = sorted(polygons, key=Within, reverse=True)

    # add levels to the sorted polygons
    # odd levels are inside, even levels are outside
    levels = [0] * len(sorted_polygons)
    for i in range(len(sorted_polygons)):
        for j in range(i):
            if sorted_polygons[j].contains(sorted_polygons[i]):
                levels[i] += 1

    # sort by level from deepest to shallowest
    sorted_polygons = sorted(
        zip(sorted_polygons, levels), key=lambda x: x[1], reverse=True
    )

    for polygon, level in sorted_polygons:
        direction = 1.0 if level % 2 == 0 else -1.0
        try:
            offset = offset_polygon(polygon, direction * args.tool / 2.0)
        except ValueError as e:
            print(f"Warning:  offsetting polygon failed: {e}")
            print("\tFix by using a smaller tool diameter")
            continue
        edges = polygon_to_path(offset)

        output += generate_route_gcode(edges, args)

    output += generate_footer(args)

    with open(args.output, "w") as file:
        file.write(output)

    print("GCode generated successfully")
