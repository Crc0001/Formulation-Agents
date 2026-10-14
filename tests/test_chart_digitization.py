import pytest
from virtual_reactor_api.chart_digitization import Geometry,convert

def geometry():
 return Geometry.model_validate(dict(readable=True,reason='test',x_unit='min',y_unit='%',x_ticks=[dict(pixel=x,value=v) for x,v in [(10,0),(60,30),(110,60)]],y_ticks=[dict(pixel=x,value=v) for x,v in [(110,0),(60,50),(10,100)]],series=[dict(label='A',legend_identity='circle',points=[dict(x=35,y=85,radius_px=2),dict(x=85,y=35,radius_px=2)])]))

def test_pixel_conversion_and_uncertainty():
 r=convert(geometry(),120,120);p=r['arms'][0]['points'][0]
 assert p['time_min']==pytest.approx(15)
 assert p['q_percent']==pytest.approx(25)
 assert p['q_error_pp']==pytest.approx(4)
 assert p['time_error_min']==pytest.approx(2.4)

def test_non_linear_and_outside_refused():
 g=geometry();g.x_ticks[1].value=5
 with pytest.raises(ValueError,match='线性'):convert(g,120,120)
 g=geometry();g.series[0].points[0].x=0
 with pytest.raises(ValueError,match='范围'):convert(g,120,120)
 g=geometry();g.readable=False
 with pytest.raises(ValueError,match='无法'):convert(g,120,120)
