import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('publication',Path(__file__).parents[1]/'scripts/verify_crossday_publication.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_publication_checks_delta_clock_timing_and_exclusions():
    before={'set_final_2h':[1,2]}
    change={'new_error':None,'new_t0_obs':'2024-01-01T00:00:00+00:00','new_t90_s':12.,'sets':{'set_final_2h':{'old_n':2,'new_n':2,'added':[3],'removed':[2]}}}
    after={'error':None,'t0_obs':change['new_t0_obs'],'t90_s':12.,'set_final_2h':[1,3]}
    assert m.check_row(before,after,change)==[]
    assert m.check_row(before,{**after,'set_final_2h':[1,2]},change)==['set_final_2h']
    assert m.check_row(before,{**after,'t90_s':13.},change)==['t90_s']
    assert m.check_row(before,{**after,'t0_obs':'2024-01-01T00:00:01+00:00'},change)==['t0_obs']
    excluded={**after,'error':'insufficient_planned_followup','set_final_2h':None,'t90_s':None}
    assert m.check_row(before,excluded,change,True)==[]
    assert 'error' in m.check_row(before,excluded,change)
    assert 'set_final_2h:excluded_not_null' in m.check_row(before,{**excluded,'set_final_2h':[]},change,True)
