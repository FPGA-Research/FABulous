import pytest

from FABulous.fabric_generator.code_generator import codeGenerator
from FABulous.FABulous_API import FABulous_API


@pytest.fixture
def test_fabric_csv(tmp_path):
    """Create a temporary test fabric CSV file."""
    csv_content = """Tile,Name,X,Y,N,S,W,E
Tile_PE,PE_0_0,0,0,1,1,1,1
"""
    csv_file = tmp_path / "test_fabric.csv"
    csv_file.write_text(csv_content)
    return csv_file


@pytest.fixture
def api_instance(tmp_path):
    """Create a FABulous_API instance with default writer."""
    writer = codeGenerator()
    writer.outFileName = str(tmp_path / "output")
    return FABulous_API(writer)


def test_init_with_empty_csv():
    """Test initialization with empty CSV path."""
    writer = codeGenerator()
    api = FABulous_API(writer)
    assert api.fileExtension == ".v"


def test_load_fabric(api_instance, test_fabric_csv):
    """Test loading fabric from CSV file."""
    api_instance.loadFabric(test_fabric_csv)
    assert api_instance.fabric is not None
    assert "PE_0_0" in api_instance.fabric.tileDic


def test_load_fabric_invalid_extension(api_instance, tmp_path):
    """Test loading fabric with invalid file extension."""
    invalid_file = tmp_path / "invalid.txt"
    invalid_file.touch()
    with pytest.raises(ValueError):
        api_instance.loadFabric(invalid_file)


def test_set_writer_output_file(api_instance, tmp_path):
    """Test setting writer output file."""
    output_dir = str(tmp_path / "test_output")
    api_instance.setWriterOutputFile(output_dir)
    assert api_instance.writer.outFileName == output_dir


def test_get_tile(api_instance, test_fabric_csv):
    """Test getting tile by name."""
    api_instance.loadFabric(test_fabric_csv)
    tile = api_instance.getTile("PE_0_0")
    assert tile is not None
    assert tile.name == "PE_0_0"


def test_get_nonexistent_tile(api_instance, test_fabric_csv):
    """Test getting non-existent tile."""
    api_instance.loadFabric(test_fabric_csv)
    tile = api_instance.getTile("NonexistentTile")
    assert tile is None


def test_gen_config_mem_invalid_tile(api_instance, test_fabric_csv, tmp_path):
    """Test generating config memory for invalid tile."""
    api_instance.loadFabric(test_fabric_csv)
    config_mem_path = tmp_path / "config_mem.v"
    with pytest.raises(ValueError):
        api_instance.genConfigMem("NonexistentTile", config_mem_path)


def test_get_bels(api_instance, test_fabric_csv):
    """Test getting all unique Bels."""
    api_instance.loadFabric(test_fabric_csv)
    bels = api_instance.getBels()
    assert isinstance(bels, list)


def test_get_tiles(api_instance, test_fabric_csv):
    """Test getting all tiles."""
    api_instance.loadFabric(test_fabric_csv)
    tiles = list(api_instance.getTiles())
    assert len(tiles) > 0
    assert tiles[0].name == "PE_0_0"
