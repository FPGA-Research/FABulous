
import csv
import os
import re
from graphviz import Digraph
from itertools import product

def expand_line(line):
    """Expands a line with bracket notation into multiple lines."""
    parts = line.split(',')
    if len(parts) != 2:
        return [line]

    dest, src = parts

    def get_options(port_str):
        if '[' not in port_str:
            return [port_str]
        
        prefix, inner, suffix = ' ', ' ', ' '
        try:
            prefix, rest = port_str.split('[', 1)
            inner, suffix = rest.split(']', 1)
        except ValueError:
            return [port_str] # Malformed

        return [f"{prefix}{opt}{suffix}" for opt in inner.split('|')]

    dest_options = get_options(dest)
    src_options = get_options(src)

    # Handle cases where the number of options is different
    if len(dest_options) > 1 and len(src_options) > 1 and len(dest_options) != len(src_options):
        # This is likely a cross product
        expanded_lines = [f'{d},{s}' for d, s in product(dest_options, src_options)]
    elif len(dest_options) > 1 and len(src_options) > 1:
        expanded_lines = [f'{d},{s}' for d, s in zip(dest_options, src_options)]
    elif len(dest_options) > 1:
        expanded_lines = [f'{d},{src_options[0]}' for d in dest_options]
    elif len(src_options) > 1:
        expanded_lines = [f'{dest_options[0]},{s}' for s in src_options]
    else:
        expanded_lines = [line]

    return expanded_lines

def parse_switch_matrix(matrix_path):
    """Parses a .list file and returns a list of (source, destination) tuples."""
    connections = []
    base_dir = os.path.dirname(matrix_path)
    
    lines_to_process = []
    with open(matrix_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('INCLUDE'):
                include_path = os.path.normpath(os.path.join(base_dir, line.split(',')[1].strip()))
                with open(include_path, 'r') as include_f:
                    lines_to_process.extend(include_f.readlines())
            else:
                lines_to_process.append(line)

    expanded_lines = []
    for line in lines_to_process:
        expanded_lines.extend(expand_line(line.strip()))

    for line in expanded_lines:
        parts = line.split(',')
        if len(parts) == 2:
            dest, src = parts
            connections.append((src, dest))
    return connections

def get_cluster_info(port_name, bels):
    """Determines the cluster and color for a given port."""
    for _, bel_prefix in bels:
        if port_name.startswith(bel_prefix):
            return 'cluster_bels', 'lightblue'

    if port_name.startswith('N'): return 'cluster_north', 'tomato'
    if port_name.startswith('S'): return 'cluster_south', 'gold'
    if port_name.startswith('E'): return 'cluster_east', 'olivedrab2'
    if port_name.startswith('W'): return 'cluster_west', 'royalblue1'
    if port_name.startswith('J'): return 'cluster_jump', 'plum'
    
    return 'cluster_other', 'lightgray'

def visualize_tile(tile_name, demo_path, output_filename):
    """Generates a detailed graphical visualization of a single FABulous tile."""
    tile_def_path = os.path.join(demo_path, 'Tile', tile_name, f'{tile_name}.csv')

    if not os.path.exists(tile_def_path):
        print(f"Tile definition file not found at {tile_def_path}")
        return

    dot = Digraph(comment=f'{tile_name} Tile', engine='dot')
    dot.attr(label=f'{tile_name} Tile - Detailed View', fontsize='24', labelloc='t')
    dot.attr('node', style='filled', shape='ellipse', fontname='Helvetica', fontsize='10')
    dot.attr('edge', arrowhead='vee', arrowsize='0.6')
    dot.attr(splines='true', overlap='prism', nodesep='0.5', ranksep='1')

    bels = []
    matrix_file = None
    with open(tile_def_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0] == 'BEL':
                bels.append((os.path.basename(row[1]).split('.')[0], row[2]))
            elif row and row[0] == 'MATRIX':
                matrix_file = row[1]

    if not matrix_file:
        print("No switch matrix file found.")
        return

    matrix_path = os.path.join(os.path.dirname(tile_def_path), matrix_file)
    connections = parse_switch_matrix(matrix_path)

    ports = set()
    for src, dest in connections:
        ports.add(src)
        ports.add(dest)

    # Define clusters
    clusters = {
        'cluster_bels': Digraph('cluster_bels'),
        'cluster_north': Digraph('cluster_north'),
        'cluster_south': Digraph('cluster_south'),
        'cluster_east': Digraph('cluster_east'),
        'cluster_west': Digraph('cluster_west'),
        'cluster_jump': Digraph('cluster_jump'),
        'cluster_other': Digraph('cluster_other')
    }
    cluster_attrs = {
        'cluster_bels': {'label': 'Logic Elements (BELs)', 'color': 'gray'},
        'cluster_north': {'label': 'North Ports', 'color': 'tomato'},
        'cluster_south': {'label': 'South Ports', 'color': 'gold'},
        'cluster_east': {'label': 'East Ports', 'color': 'olivedrab2'},
        'cluster_west': {'label': 'West Ports', 'color': 'royalblue1'},
        'cluster_jump': {'label': 'Jump Wires', 'color': 'plum'},
        'cluster_other': {'label': 'Other', 'color': 'lightgray'}
    }

    for name, graph in clusters.items():
        graph.attr(style='rounded', label=cluster_attrs[name]['label'], color=cluster_attrs[name]['color'], fontname='Helvetica')

    # Add nodes to appropriate clusters
    for port in sorted(list(ports)):
        cluster_name, color = get_cluster_info(port, bels)
        shape = 'record' if cluster_name == 'cluster_bels' else 'ellipse'
        clusters[cluster_name].node(port, label=port, fillcolor=color, shape=shape)

    for g in clusters.values():
        dot.subgraph(g)

    # Add edges
    for src, dest in connections:
        dot.edge(src, dest)

    output_path = os.path.join(os.getcwd(), output_filename)
    dot.render(output_path, view=False, format='png')
    print(f"Detailed tile visualization saved to {output_path}.png")

if __name__ == '__main__':
    visualize_tile('LUT4AB', '/home/jart/work/uni/FABulous/demo', 'LUT4AB_visualization_detailed')
