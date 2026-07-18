import pytest
from app.kernel.compute.equivalence_engine import EqualitySaturation, EquivalentAlternative

def test_extracts_cheapest_verified_equivalent():
    engine=EqualitySaturation()
    engine.add(EquivalentAlternative('cloud','repair',100,True))
    engine.add(EquivalentAlternative('local','repair',5,True))
    engine.add(EquivalentAlternative('unsafe','repair',1,False))
    assert engine.extract('repair').expression_id == 'local'
    with pytest.raises(LookupError): engine.extract('missing')
    assert engine.summary()=={"groups":1,"alternatives":3,"verified":2}
    with pytest.raises(ValueError): engine.add(EquivalentAlternative('local','repair',2,True))
