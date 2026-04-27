import pytest
from unittest.mock import patch, MagicMock
import tkinter as tk

from contextcruncher.ui.snipper import SnippingTool

@pytest.fixture
def mock_tk_manager():
    with patch("contextcruncher.ui.snipper.get_tk_manager") as mock_get:
        manager = MagicMock()
        manager.root = MagicMock()
        # Mock schedule to immediately execute the function instead of queuing
        manager.schedule.side_effect = lambda f: f()
        mock_get.return_value = manager
        yield mock_get

@pytest.fixture
def mock_image_grab():
    with patch("contextcruncher.ui.snipper.ImageGrab") as mock_ig:
        mock_ig.grab.return_value = "mock_image"
        yield mock_ig

def test_snipping_tool_success(mock_tk_manager, mock_image_grab):
    callback_called = False
    captured_image = None
    captured_bbox = None

    def mock_callback(image, bbox):
        nonlocal callback_called, captured_image, captured_bbox
        callback_called = True
        captured_image = image
        captured_bbox = bbox

    # Mock tkinter components
    with patch("contextcruncher.ui.snipper.tk.Toplevel") as MockToplevel, \
         patch("contextcruncher.ui.snipper.tk.Canvas") as MockCanvas, \
         patch("contextcruncher.ui.snipper.ctypes.windll.user32"):
        
        mock_win = MagicMock()
        mock_win.winfo_rootx.return_value = 10
        mock_win.winfo_rooty.return_value = 10
        MockToplevel.return_value = mock_win
        
        tool = SnippingTool(callback=mock_callback)
        # Mock wait so we don't block
        tool.done.wait = MagicMock()

        # Execute start (which calls _create_overlay)
        tool.start()
        
        # Simulate pressing mouse
        press_event = MagicMock(x_root=100, y_root=100)
        tool._on_press(press_event)
        
        # Simulate dragging
        drag_event = MagicMock(x_root=200, y_root=200)
        tool._on_drag(drag_event)
        
        # Simulate releasing mouse
        release_event = MagicMock(x_root=250, y_root=300)
        tool._on_release(release_event)
        
        assert callback_called
        assert captured_image == "mock_image"
        assert captured_bbox == (100, 100, 250, 300)
        mock_image_grab.grab.assert_called_with(bbox=(100, 100, 250, 300), all_screens=True)

def test_snipping_tool_zero_size(mock_tk_manager, mock_image_grab):
    callback_called = False
    captured_image = "should_be_none"
    
    def mock_callback(image, bbox):
        nonlocal callback_called, captured_image
        callback_called = True
        captured_image = image

    with patch("contextcruncher.ui.snipper.tk.Toplevel") as MockToplevel, \
         patch("contextcruncher.ui.snipper.tk.Canvas") as MockCanvas, \
         patch("contextcruncher.ui.snipper.ctypes.windll.user32"), \
         patch("contextcruncher.ui.snipper.show_toast") as mock_toast:
        
        tool = SnippingTool(callback=mock_callback)
        tool.done.wait = MagicMock()
        tool.start()
        
        # Simulate click without drag (0x0)
        press_event = MagicMock(x_root=100, y_root=100)
        tool._on_press(press_event)
        
        release_event = MagicMock(x_root=101, y_root=101)
        tool._on_release(release_event)
        
        assert callback_called
        assert captured_image is None
        mock_toast.assert_called_once()
        mock_image_grab.grab.assert_not_called()

def test_snipping_tool_escape(mock_tk_manager, mock_image_grab):
    callback_called = False
    captured_image = "should_be_none"
    
    def mock_callback(image, bbox):
        nonlocal callback_called, captured_image
        callback_called = True
        captured_image = image

    with patch("contextcruncher.ui.snipper.tk.Toplevel") as MockToplevel, \
         patch("contextcruncher.ui.snipper.tk.Canvas") as MockCanvas, \
         patch("contextcruncher.ui.snipper.ctypes.windll.user32"):
        
        tool = SnippingTool(callback=mock_callback)
        tool.done.wait = MagicMock()
        tool.start()
        
        # Simulate escape
        tool._on_escape(MagicMock())
        
        assert callback_called
        assert captured_image is None
        mock_image_grab.grab.assert_not_called()
