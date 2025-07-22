
import yaml
import os

def yaml_to_csv(yaml_data, output_path):
    with open(output_path, 'w') as f:
        tile = yaml_data
        line = f"TILE,{tile['name']},,,,,#carry out,,,,,,,,,,,," + "\n"
        f.write(line)
        if 'include' in tile:
            line = f"INCLUDE,{tile['include']}" + "\n"
            f.write(line)
        if 'connections' in tile:
            for conn in tile['connections']:
                line = f"{conn['type']},{conn['source']},{conn['offset'][0]},{conn['offset'][1]},{conn['destination']},{conn['wires']},# carry,,,,,,,,,,,," + "\n"
                f.write(line)
        if 'jumps' in tile:
            for jump in tile['jumps']:
                line = f"JUMP,{jump['source']},0,0,{jump['destination']},{jump['wires']},,,,,,,,,,,,,,," + "\n"
                f.write(line)
        if 'bels' in tile:
            for bel in tile['bels']:
                line = f"BEL,{bel['path']},{bel.get('name', '')},,,,,,,,,,,,,,,,," + "\n"
                f.write(line)
        if 'matrix' in tile:
            line = f"MATRIX,{tile['matrix']},,,,,,,,,,,,,,,,,,," + "\n"
            f.write(line)
        line = "EndTILE,,,,,,,,,,,,,,,,,,," + "\n"
        f.write(line)


def yaml_to_list(yaml_data, output_path):
    with open(output_path, 'w') as f:
        matrix = yaml_data
        if 'includes' in matrix:
            for include in matrix['includes']:
                line = f"INCLUDE, {include}\n"
                f.write(line)
        f.write("\n")
        if 'connections' in matrix:
            for conn in matrix['connections']:
                line = f"{conn['destination']},{conn['sources']}\n"
                f.write(line)


def main():
    # Create a dummy combined YAML file for testing
    with open("LUT4AB_full.yaml", "w") as f:
        f.write("""
tile_definition:
  tile:
    name: LUT4AB
    include: ../include/Base.csv
    connections:
      - type: NORTH
        source: Co
        offset: [0, -1]
        destination: Ci
        wires: 1
    jumps:
      - source: J_SR_BEG
        destination: J_SR_END
        wires: 1
      - source: J_EN_BEG
        destination: J_EN_END
        wires: 1
    bels:
      - path: ./LUT4c_frame_config_dffesr.v
        name: LA_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LB_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LC_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LD_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LE_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LF_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LG_
      - path: ./LUT4c_frame_config_dffesr.v
        name: LH_
      - path: ./MUX8LUT_frame_config_mux.v
    matrix: ./LUT4AB_switch_matrix.list # This path is still needed for the CSV output

  switch_matrix:
    includes:
      - ../include/Base.list
    connections:
      - destination: "L[A|B]_I0"
        sources: "[J2MID_ABa_END0|J2MID_ABa_END0]"
      - destination: "L[A|B]_I1"
        sources: "[J2MID_ABa_END1|J2MID_ABa_END1]"
""")

    with open("LUT4AB_full.yaml", 'r') as f:
        full_data = yaml.safe_load(f)

    tile_data = full_data['tile_definition']['tile']
    switch_matrix_data = full_data['tile_definition']['switch_matrix']

    os.makedirs("output", exist_ok=True)
    yaml_to_csv(tile_data, "output/LUT4AB.csv")
    yaml_to_list(switch_matrix_data, "output/LUT4AB_switch_matrix.list")

if __name__ == "__main__":
    main()
