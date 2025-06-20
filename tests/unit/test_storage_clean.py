import pytest
from content_collector.storage.database import DatabaseManager

@pytest.fixture
def db_manager():
    return DatabaseManager()

def test_database_manager_creation(db_manager):
    """Test that DatabaseManager can be instantiated."""
    assert db_manager is not None
    assert hasattr(db_manager, 'initialize')
    assert hasattr(db_manager, 'health_check')

def test_database_manager_methods(db_manager):
    """Test that DatabaseManager has expected methods."""
    assert hasattr(db_manager, 'create_tables')
    assert hasattr(db_manager, 'close')
