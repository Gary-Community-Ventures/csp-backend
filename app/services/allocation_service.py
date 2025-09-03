"""
Service for managing monthly allocations across the application.
Centralizes logic for creating, fetching, and processing allocations.
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from ..extensions import db
from ..models.month_allocation import MonthAllocation
from ..sheets.helpers import format_name
from ..sheets.mappings import ChildColumnNames, get_children


class AllocationResult:
    """Container for allocation processing results."""

    def __init__(self):
        self.created_count = 0
        self.skipped_count = 0
        self.error_count = 0
        self.errors: List[str] = []
        self.allocations_created: List[MonthAllocation] = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for API responses."""
        return {
            "created_count": self.created_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "errors": self.errors[:10],  # Limit to first 10 for logging
            "allocations_created": len(self.allocations_created),
        }


class AllocationService:
    """Service for managing monthly allocations."""

    def __init__(self, app=None):
        """Initialize the allocation service."""
        self.app = app or current_app

    def create_allocations_for_all_children(
        self,
        target_month: date,
        dry_run: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> AllocationResult:
        """
        Create allocations for all children for a specific month.

        Args:
            target_month: The month to create allocations for (should be first day of month)
            dry_run: If True, don't actually create allocations, just simulate
            progress_callback: Optional callback for progress updates

        Returns:
            AllocationResult with details about created allocations
        """
        result = AllocationResult()

        # Fetch all children from Google Sheets
        try:
            all_children = get_children()
        except Exception as e:
            self.app.logger.error(f"Failed to fetch children from Google Sheets: {e}")
            raise

        if not all_children:
            self.app.logger.warning("No children found in Google Sheets")
            return result

        # Process each child
        for child_data in all_children:
            child_result = self._process_single_child(child_data, target_month, dry_run)

            # Update counters based on result
            if child_result[0] == "created":
                result.created_count += 1
                if child_result[1]:  # The allocation object
                    result.allocations_created.append(child_result[1])
            elif child_result[0] == "skipped":
                result.skipped_count += 1
            elif child_result[0] == "error":
                result.error_count += 1
                if child_result[2]:  # The error message
                    result.errors.append(child_result[2])

            # Call progress callback if provided
            if progress_callback:
                progress_callback(child_data, child_result[0])

        # Commit all changes if not dry run
        if not dry_run and result.created_count > 0:
            try:
                db.session.commit()
                self.app.logger.info(
                    f"Successfully committed {result.created_count} allocations for {target_month.strftime('%B %Y')}"
                )
            except Exception as e:
                db.session.rollback()
                self.app.logger.error(f"Failed to commit allocations: {e}")
                raise

        return result

    def create_allocations_for_specific_children(
        self,
        child_ids: List[str],
        target_month: date,
    ) -> AllocationResult:
        """
        Create allocations for specific children.

        Args:
            child_ids: List of child IDs to create allocations for
            target_month: The month to create allocations for

        Returns:
            AllocationResult with details about created allocations
        """
        result = AllocationResult()

        # Fetch all children and filter
        try:
            all_children = get_children()
            children_to_process = [c for c in all_children if c.get(ChildColumnNames.ID) in child_ids]
        except Exception as e:
            self.app.logger.error(f"Failed to fetch children from Google Sheets: {e}")
            raise

        if not children_to_process:
            self.app.logger.warning(f"No matching children found for IDs: {child_ids}")
            return result

        # Process each child
        for child_data in children_to_process:
            child_result = self._process_single_child(child_data, target_month, dry_run=False)

            if child_result[0] == "created":
                result.created_count += 1
                if child_result[1]:
                    result.allocations_created.append(child_result[1])
            elif child_result[0] == "skipped":
                result.skipped_count += 1
            elif child_result[0] == "error":
                result.error_count += 1
                if child_result[2]:
                    result.errors.append(child_result[2])

        # Commit changes
        if result.created_count > 0:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                self.app.logger.error(f"Failed to commit allocations for specific children: {e}")
                raise

        return result

    def _process_single_child(
        self,
        child_data: Dict,
        target_month: date,
        dry_run: bool = False,
    ) -> Tuple[str, Optional[MonthAllocation], Optional[str]]:
        """
        Process allocation creation for a single child.

        Returns:
            Tuple of (status, allocation, error_message)
            where status is one of: 'created', 'skipped', 'error'
        """
        child_id = child_data.get(ChildColumnNames.ID)
        child_name = format_name(child_data)

        # Validate child ID
        if not child_id:
            error_msg = f"Missing ID for child: {child_name}"
            self.app.logger.warning(error_msg)
            return ("error", None, error_msg)

        try:
            # Check if allocation already exists
            existing_allocation = MonthAllocation.query.filter_by(
                google_sheets_child_id=child_id, date=target_month
            ).first()

            if existing_allocation:
                self.app.logger.debug(f"Allocation already exists for {child_name} ({child_id}) for {target_month}")
                return ("skipped", existing_allocation, None)

            if dry_run:
                self.app.logger.info(
                    f"[DRY RUN] Would create allocation for {child_name} ({child_id}) for {target_month}"
                )
                return ("created", None, None)

            # Create new allocation
            allocation = MonthAllocation.get_or_create_for_month(child_id, target_month)

            self.app.logger.info(
                f"Created allocation for {child_name} ({child_id}): ${allocation.allocation_cents / 100:.2f}"
            )
            return ("created", allocation, None)

        except ValueError as e:
            # Handle specific validation errors
            error_msg = f"{child_name} ({child_id}): {str(e)}"
            self.app.logger.error(f"Validation error creating allocation: {error_msg}")
            return ("error", None, error_msg)

        except Exception as e:
            # Handle unexpected errors
            error_msg = f"{child_name} ({child_id}): {str(e)}"
            self.app.logger.error(f"Unexpected error creating allocation: {error_msg}")
            return ("error", None, error_msg)

    def get_or_create_allocation(self, child_id: str, target_month: date) -> MonthAllocation:
        """
        Simple wrapper around MonthAllocation.get_or_create_for_month with logging.

        Args:
            child_id: The child's Google Sheets ID
            target_month: The month to get/create allocation for

        Returns:
            The MonthAllocation instance
        """
        allocation = MonthAllocation.get_or_create_for_month(child_id, target_month)
        self.app.logger.debug(f"Got/created allocation for child {child_id}: {allocation}")
        return allocation
