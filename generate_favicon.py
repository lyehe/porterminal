"""Generate PTN favicon SVG from ASCII art grid."""

# Define PTN as ASCII art (16x16 grid)
# Use . for empty, # for filled
GRID = """
................
................
.###............
..###...........
...###..........
....###.........
...###..........
..###...........
.###....#####...
........#####...
................
................
................
................
................
................
"""

# Gradient colors from top to bottom (16 rows)
GRADIENT = [
    "#5EEAD4",  # 0
    "#4FE0D0",  # 1
    "#40D6CC",  # 2
    "#31CCC8",  # 3
    "#2CC5D4",  # 4
    "#27BEE0",  # 5
    "#22B7EC",  # 6
    "#38BDF8",  # 7
    "#3AABF4",  # 8
    "#3C99F0",  # 9
    "#3E87EC",  # 10
    "#3B82F6",  # 11
    "#3575F2",  # 12
    "#2F68EE",  # 13
    "#2563EB",  # 14
    "#1D4ED8",  # 15
]


def get_color(y):
    if y < len(GRADIENT):
        return GRADIENT[y]
    return GRADIENT[-1]


def generate_svg():
    lines = [line for line in GRID.strip().split("\n") if line]

    color = "#FFFFFF"
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">',
        '  <rect width="16" height="16" fill="#1e1e1e"/>',
    ]

    for y, line in enumerate(lines):
        for x, char in enumerate(line):
            if char == "#":
                svg.append(f'  <rect x="{x}" y="{y}" width="1" height="1" fill="{color}"/>')

    svg.append("</svg>")
    return "\n".join(svg)


if __name__ == "__main__":
    svg = generate_svg()
    print(svg)

    with open("porterminal/static/icon.svg", "w") as f:
        f.write(svg)
    print("\nSaved to porterminal/static/icon.svg")
