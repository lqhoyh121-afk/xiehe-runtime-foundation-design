from fixtures import fixture
from validator import validate_projection


def test_published_projection_is_locally_validated_not_authorized():
    f = fixture()
    result = validate_projection(f.projection, f.authority, f.context)
    assert result['verdict'] == 'VALIDATED_LOCAL_ONLY'
    assert result['contract_status'] == 'DRAFT'
    assert result['production_authorized'] is False
