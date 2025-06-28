
import csv
import os
import re
from graphviz import Digraph

def visualize_fabric(fabric_csv_path, output_filename):
    """
    Generates a graphical visualization of the FABulous fabric.

    Args:
        fabric_csv_path (str): The path to the fabric.csv file.
        output_filename (str): The name of the output image file (e.g., "fabric_visualization.png").
    """

    dot = Digraph(comment='FABulous Fabric', graph_attr={'splines': 'ortho', 'nodesep': '1', 'ranksep': '1'})
    dot.attr('node', shape='box', style='rounded')

    fabric_dir = os.path.dirname(fabric_csv_path)
    tiles = []
    with open(fabric_csv_path, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0] == 'FabricBegin':
                break
        for row in reader:
            if row and row[0] == 'FabricEnd':
                break
            tiles.append([cell for cell in row if cell])

    with dot.subgraph(name='cluster_fabric') as c:
        c.attr(label='Fabric')
        for r, row in enumerate(tiles):
            for c, tile_name in enumerate(row):
                if tile_name and tile_name != '#':
                    with dot.subgraph(name=f'cluster_{r}_{c}') as tile_graph:
                        tile_graph.attr(label=tile_name)
                        tile_def_path = os.path.join(fabric_dir, 'Tile', tile_name, f'{tile_name}.csv')
                        if os.path.exists(tile_def_path):
                            with open(tile_def_path, 'r') as tile_f:
                                tile_reader = csv.reader(tile_f)
                                for tile_row in tile_reader:
                                    if tile_row and tile_row[0] == 'BEL':
                                        bel_name = tile_row[1].split('/')[-1]
                                        tile_graph.node(f'{r}_{c}_{bel_name}', label=bel_name, shape='ellipse')
                                    if tile_row and tile_row[0] == 'MATRIX':
                                        matrix_file = tile_row[1]
                                        matrix_path = os.path.join(os.path.dirname(tile_def_path), matrix_file)
                                        if os.path.exists(matrix_path):
                                            with open(matrix_path, 'r') as matrix_f:
                                                for line in matrix_f:
                                                    line = line.strip()
                                                    if line and not line.startswith('#'):
                                                        if 'INCLUDE' in line:
                                                            continue
                                                        parts = line.split(',')
                                                        if len(parts) == 2:
                                                            src, dest = parts
                                                            src_port = src.split('[')[0]
                                                            dest_port = dest.split('[')[0]
                                                            tile_graph.edge(f'{r}_{c}_{src_port}', f'{r}_{c}_{dest_port}')


    dot.render(output_filename, view=False, format='png')
    print(f"Fabric visualization saved to {output_filename}.png")

if __name__ == '__main__':
    visualize_fabric('/home/jart/work/uni/FABulous/demo/fabric.csv', 'fabric_visualization')
