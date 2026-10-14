import pytest
from auto_editions_print import describe,exact_export_geometry

def test_framed_a1_never_leaks_to_unframed_xl():
    m=dict(dimensions=[8505,6012],source_dimensions=[2835,2004])
    assert describe('Unframed / XL',m)['effective_ppi'] is None
    with pytest.raises(ValueError,match='unframed'):describe('Unframed / XL',m,'GLOBAL-CFP-A1')
    framed=describe('Black / XL',m,'GLOBAL-CFP-A1')
    assert framed['supplier']['pixel_dimensions']==[9933,7016]
    assert framed['print_status']=='TEST / NOT PRINT READY'
    with pytest.raises(ValueError,match='ratio'):exact_export_geometry(m['dimensions'],'GLOBAL-CFP-A1')
