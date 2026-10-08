"""Headless tests for the Textual TUI interface."""

import pytest
from rdr_transit.tui.app import RDRTransitApp


@pytest.mark.asyncio
async def test_tui_mount_and_widgets():
    app = RDRTransitApp()
    async with app.run_test() as pilot:
        # Check that main widgets are mounted and present
        assert app.query_one("#peer-table") is not None
        assert app.query_one("#staging-list") is not None
        assert app.query_one("#receiver-panel") is not None
        assert app.query_one("#btn-scan") is not None
        assert app.query_one("#btn-send") is not None

        # Verify key navigation actions
        await pilot.press("d")  # Scan peers action
        await pilot.pause()

        await pilot.press("question_mark")  # Show help dialog
        await pilot.pause()
        assert len(app.screen_stack) > 1  # Modal screen pushed

        await pilot.press("enter")  # Close help dialog
        await pilot.pause()
