"""
Reusable Supabase mock utilities for testing.

This module provides generic, extensible mocking infrastructure for Supabase
tables and queries to simplify test setup across the codebase.
"""

from datetime import date, datetime
from typing import Any, Dict, List


class DictWithAttributes(dict):
    """Dict that allows attribute access to its keys."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value


class MockSupabaseResponse:
    """Mock Supabase response object."""

    def __init__(self, data: Any, error: Any = None):
        # Convert dicts to DictWithAttributes for attribute access
        if isinstance(data, list):
            self.data = [DictWithAttributes(d) if isinstance(d, dict) else d for d in data]
        elif isinstance(data, dict):
            self.data = DictWithAttributes(data)
        else:
            self.data = data
        self.error = error

    def __iter__(self):
        """Make response iterable to support for loops over data."""
        if self.data and isinstance(self.data, list):
            return iter(self.data)
        elif self.data:
            return iter([self.data])
        return iter([])


class MockSupabaseQuery:
    """Mock Supabase query builder for chainable queries."""

    def __init__(self, data: List[Dict] = None):
        self.data = data if data is not None else []
        self._filters = []
        self._single = False

    def select(self, *args, **kwargs):
        """Mock select method."""
        return self

    def eq(self, column: str, value: Any):
        """Mock eq filter."""
        self._filters.append(("eq", column, value))
        return self

    def single(self):
        """Mock single result method."""
        self._single = True
        return self

    def execute(self):
        """Mock execute method that returns filtered data."""
        result = self.data

        # Apply filters
        for filter_type, column, value in self._filters:
            if filter_type == "eq":
                result = [r for r in result if r.get(column) == value]

        # Return single item if requested
        if self._single:
            if result:
                return MockSupabaseResponse(result[0])
            # Return response with None data and error to match Supabase behavior
            return MockSupabaseResponse(None, error={"message": "No results found", "code": "PGRST116"})

        return MockSupabaseResponse(result)


class MockSupabaseTable:
    """Mock for a Supabase table."""

    def __init__(self, table_name: str, data: List[Dict] = None):
        self.table_name = table_name
        self.data = data if data is not None else []

    def select(self, *args, **kwargs):
        """Create a new query with this table's data."""
        query = MockSupabaseQuery(self.data)
        return query.select(*args, **kwargs)

    def insert(self, data: Dict):
        """Mock insert method."""
        self.data.append(data)
        return MockSupabaseResponse(data)

    def update(self, data: Dict):
        """Mock update method."""
        return MockSupabaseQuery([data])

    def delete(self):
        """Mock delete method."""
        return MockSupabaseQuery([])


class MockSupabaseClient:
    """Mock Supabase client."""

    def __init__(self):
        self.tables = {}

    def table(self, table_name: str):
        """Get or create a mock table."""
        if table_name not in self.tables:
            self.tables[table_name] = MockSupabaseTable(table_name)
        return self.tables[table_name]

    def add_table_data(self, table_name: str, data: List[Dict]):
        """Add data to a specific table."""
        if table_name not in self.tables:
            self.tables[table_name] = MockSupabaseTable(table_name, data)
        else:
            self.tables[table_name].data.extend(data)


def create_mock_supabase_client(initial_data: Dict[str, List[Dict]] = None) -> MockSupabaseClient:
    """
    Create a mock Supabase client with optional initial data.

    Args:
        initial_data: Dictionary mapping table names to lists of row data

    Returns:
        MockSupabaseClient instance
    """
    client = MockSupabaseClient()

    if initial_data:
        for table_name, rows in initial_data.items():
            client.add_table_data(table_name, rows)

    return client


def create_mock_child_data(
    child_id: int = 1,
    family_id: int = 1,
    first_name: str = "Test",
    last_name: str = "Child",
    monthly_allocation: float = 1000.0,
    prorated_allocation: float = 500.0,
    status: str = "active",
    payment_enabled: bool = True,
    **kwargs,
) -> Dict:
    """Create mock child data with sensible defaults."""
    data = {
        "id": child_id,
        "family_id": family_id,
        "first_name": first_name,
        "last_name": last_name,
        "dob": date(2020, 1, 1).isoformat(),
        "monthly_allocation": monthly_allocation,
        "prorated_allocation": prorated_allocation,
        "status": status,
        "payment_enabled": payment_enabled,
        "created_at": datetime.now().isoformat(),
    }
    data.update(kwargs)
    return data


def create_mock_provider_data(
    provider_id: int = 1,
    name: str = "Test Provider",
    first_name: str = "Provider",
    last_name: str = "Name",
    email: str = "provider@test.com",
    phone: str = "555-0100",
    status: str = "active",
    type: str = "individual",
    payment_enabled: bool = True,
    **kwargs,
) -> Dict:
    """Create mock provider data with sensible defaults."""
    data = {
        "id": provider_id,
        "name": name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "status": status,
        "type": type,
        "payment_enabled": payment_enabled,
        "address_1": "123 Test St",
        "city": "Test City",
        "state": "TS",
        "zip": "12345",
        "language": "english",
        "created_at": datetime.now().isoformat(),
    }
    data.update(kwargs)
    return data


def create_mock_family_data(
    family_id: int = 1,
    size: int = 4,
    yearly_income: float = 50000.0,
    zip_code: str = "12345",
    language: str = "english",
    **kwargs,
) -> Dict:
    """Create mock family data with sensible defaults."""
    data = {
        "id": family_id,
        "size": size,
        "yearly_income": yearly_income,
        "zip": zip_code,
        "language": language,
        "created_at": datetime.now().isoformat(),
    }
    data.update(kwargs)
    return data


def create_mock_guardian_data(
    guardian_id: int = 1,
    family_id: int = 1,
    is_primary: bool = True,
    first_name: str = "Guardian",
    last_name: str = "Name",
    email: str = "guardian@test.com",
    phone_number: str = "555-0200",
    **kwargs,
) -> Dict:
    """Create mock guardian data with sensible defaults."""
    data = {
        "id": guardian_id,
        "family": family_id,
        "is_primary": is_primary,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number,
        "address_1": "456 Test Ave",
        "city": "Test Town",
        "state": "TS",
        "zip": "12345",
        "created_at": datetime.now().isoformat(),
    }
    data.update(kwargs)
    return data


def create_mock_provider_child_mapping(mapping_id: int = 1, provider_id: int = 1, child_id: int = 1, **kwargs) -> Dict:
    """Create mock provider-child mapping data."""
    data = {
        "id": mapping_id,
        "provider_id": provider_id,
        "child_id": child_id,
        "created_at": datetime.now().isoformat(),
    }
    data.update(kwargs)
    return data


def setup_child_provider_relationship(
    app,
    child_id="child123",
    family_id=123,
    provider_id="providerABC",
    child_payment_enabled=True,
    provider_payment_enabled=True,
    associate_provider=True,
    **kwargs,
):
    """
    Helper to set up child and provider data with their relationship.

    Args:
        app: Flask app with supabase_client
        child_id: ID for the child
        family_id: Family ID the child belongs to
        provider_id: ID for the provider
        child_payment_enabled: Whether child has payment enabled
        provider_payment_enabled: Whether provider has payment enabled
        associate_provider: Whether to associate provider with child
        **kwargs: Additional attributes for child or provider

    Returns:
        Tuple of (child_data, provider_data)
    """
    child_kwargs = {k: v for k, v in kwargs.items() if k.startswith("child_")}
    provider_kwargs = {k: v for k, v in kwargs.items() if k.startswith("provider_")}

    child_data = create_mock_child_data(
        child_id=child_id,
        family_id=family_id,
        payment_enabled=child_payment_enabled,
        **{k.replace("child_", ""): v for k, v in child_kwargs.items()},
    )
    provider_data = create_mock_provider_data(
        provider_id=provider_id,
        payment_enabled=provider_payment_enabled,
        **{k.replace("provider_", ""): v for k, v in provider_kwargs.items()},
    )

    # Set up the relationship
    if associate_provider:
        child_data["provider"] = [provider_data]
        # Also set up reverse relationship for provider queries
        provider_data["child"] = [child_data]
    else:
        child_data["provider"] = []
        provider_data["child"] = []

    # Add to the mock Supabase client
    app.supabase_client.tables["child"].data = [child_data]
    app.supabase_client.tables["provider"].data = [provider_data]

    return child_data, provider_data


def setup_standard_test_data() -> Dict[str, List[Dict]]:
    """
    Create a standard set of test data for common testing scenarios.

    Returns:
        Dictionary of table names to test data
    """
    # Create base data
    providers = [
        create_mock_provider_data(provider_id=1),
        create_mock_provider_data(provider_id=2, name="Second Provider", email="provider2@test.com"),
    ]

    children = [
        create_mock_child_data(child_id=1, family_id=1),
        create_mock_child_data(child_id=2, family_id=1, first_name="Second", monthly_allocation=800.0),
        create_mock_child_data(child_id=3, family_id=2, first_name="Third"),
    ]

    # Add provider relationships to children for joined queries
    # Child 1 has provider 1
    children[0]["provider"] = [providers[0]]
    children[0]["child"] = [children[0]]  # Provider queries expect child under provider

    # Child 2 has providers 1 and 2
    children[1]["provider"] = [providers[0], providers[1]]
    children[1]["child"] = [children[1]]

    # Child 3 has provider 1
    children[2]["provider"] = [providers[0]]
    children[2]["child"] = [children[2]]

    # Add child relationships to providers for joined queries
    providers[0]["child"] = [children[0], children[1], children[2]]
    providers[1]["child"] = [children[1]]

    return {
        "family": [
            create_mock_family_data(family_id=1),
            create_mock_family_data(family_id=2, size=3, yearly_income=75000.0),
        ],
        "guardian": [
            create_mock_guardian_data(guardian_id=1, family_id=1),
            create_mock_guardian_data(guardian_id=2, family_id=2),
        ],
        "child": children,
        "provider": providers,
        "provider_child_mapping": [
            create_mock_provider_child_mapping(mapping_id=1, provider_id=1, child_id=1),
            create_mock_provider_child_mapping(mapping_id=2, provider_id=1, child_id=2),
            create_mock_provider_child_mapping(mapping_id=3, provider_id=1, child_id=3),
            create_mock_provider_child_mapping(mapping_id=4, provider_id=2, child_id=2),
        ],
    }
