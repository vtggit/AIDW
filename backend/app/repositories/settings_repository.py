"""Settings repository — abstract interface."""


class SettingsRepository:
    """Abstract settings repository.

    Settings behave as a single logical record, so the interface is
    simplified to get and update operations.
    """

    def get_settings(self) -> dict | None:
        """Return the current settings record, or None if not yet created."""
        raise NotImplementedError

    def update_settings(self, payload: dict) -> dict | None:
        """Merge *payload* into the existing settings record.

        Creates the record if it does not yet exist.
        Returns the full updated record, or None on failure.
        """
        raise NotImplementedError
