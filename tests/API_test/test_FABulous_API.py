import pytest
from pathlib import Path
from FABulous.FABulous_API import FABulous_API
from FABulous.fabric_generator.code_generation_Verilog import VerilogWriter

@pytest.fixture
def fab_api(monkeypatch):
    monkeypatch.setenv("FAB_PROJ_DIR", "/home/jart/work/uni/FABulous")
    writer = VerilogWriter()
    api = FABulous_API(writer)
    api.loadFabric(Path('/home/jart/work/uni/FABulous/tests/API_test/fabric.csv'))
    return api

def test_init(fab_api):
    assert fab_api.fileExtension == ".v"

def test_load_fabric(fab_api):
    assert fab_api.fabric is not None
    assert fab_api.fabric.numberOfRows == 1
    assert fab_api.fabric.numberOfColumns == 1
    assert len(fab_api.fabric.tileDic) == 1
    assert "my_tile" in fab_api.fabric.tileDic

def test_set_writer_output_file(fab_api):
    fab_api.setWriterOutputFile("/tmp/test")
    assert fab_api.writer.outFileName == "/tmp/test"

def test_get_bels(fab_api):
    bels = fab_api.getBels()
    assert len(bels) == 1
    assert bels[0].prefix == ""

def test_get_tile(fab_api):
    tile = fab_api.getTile("my_tile")
    assert tile is not None
    assert tile.name == "my_tile"


def test_get_tiles(fab_api):
    tiles = fab_api.getTiles()
    assert len(list(tiles)) == 1
    assert list(tiles)[0].name == "my_tile"

def test_gen_tile(fab_api, tmp_path):
    output_file = tmp_path / "my_tile.v"
    fab_api.setWriterOutputFile(str(output_file))
    fab_api.genTile("my_tile")
    assert output_file.exists()

def test_gen_fabric(fab_api, tmp_path):
    output_file = tmp_path / "fabric.v"
    fab_api.setWriterOutputFile(str(output_file))
    fab_api.genFabric()
    assert output_file.exists()

def test_gen_top_wrapper(fab_api, tmp_path):
    output_file = tmp_path / "top.v"
    fab_api.setWriterOutputFile(str(output_file))
    fab_api.genTopWrapper()
    assert output_file.exists()

def test_gen_geometry(fab_api, tmp_path):
    output_file = tmp_path / "geometry.csv"
    fab_api.setWriterOutputFile(str(output_file))
    fab_api.genGeometry()
    assert output_file.exists()

def test_gen_bitstream_spec(fab_api):
    spec = fab_api.genBitStreamSpec()
    assert spec is not None

def test_gen_routing_model(fab_api):
    model = fab_api.genRoutingModel()
    assert model is not None
