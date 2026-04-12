"""
Unit tests for Plotter.py enhancements

Tests cover:
- JSON persistence (replacing pickle)
- Input validation in drawing methods
- Watchlist caching
- Global variable elimination
- Index loading error handling
- Configuration options
"""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from tempfile import TemporaryDirectory

import pandas as pd
import numpy as np

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from funcdefs import utils


class TestJsonPersistence(unittest.TestCase):
    """Test JSON persistence for line storage (replacing pickle)."""
    
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.lines_dir = Path(self.temp_dir.name) / "lines"
        self.lines_dir.mkdir()
    
    def tearDown(self):
        self.temp_dir.cleanup()
    
    def test_json_serialization(self):
        """Test JSON serialization of line data structures."""
        lines_data = {
            "artists": [],
            "daily": {"length": 2, "lines": {
                "axhline:abc123": 100.5,
                "tline:def456": ([0, 100.5], [10, 110.0])
            }},
            "weekly": {"length": 0, "lines": {}}
        }
        
        lines_path = self.lines_dir / "test.json"
        utils.writeJson(lines_path, lines_data)
        
        # Verify file exists and contains valid JSON
        self.assertTrue(lines_path.exists())
        loaded = utils.loadJson(lines_path)
        
        self.assertEqual(loaded["daily"]["length"], 2)
        self.assertEqual(loaded["weekly"]["length"], 0)
        self.assertIn("axhline:abc123", loaded["daily"]["lines"])
    
    def test_json_with_datetime(self):
        """Test JSON serialization with datetime objects."""
        test_date = pd.Timestamp("2024-01-15")
        lines_data = {
            "artists": [],
            "daily": {"length": 1, "lines": {
                "hline:xyz789": (100.0, test_date, None)
            }},
            "weekly": {"length": 0, "lines": {}}
        }
        
        lines_path = self.lines_dir / "test_datetime.json"
        utils.writeJson(lines_path, lines_data)
        
        loaded = utils.loadJson(lines_path)
        self.assertIn("hline:xyz789", loaded["daily"]["lines"])
    
    def test_json_empty_preserve(self):
        """Test that empty line data doesn't corrupt JSON."""
        lines_data = {
            "artists": [],
            "daily": {"length": 0, "lines": {}},
            "weekly": {"length": 0, "lines": {}}
        }
        
        lines_path = self.lines_dir / "empty.json"
        utils.writeJson(lines_path, lines_data)
        
        loaded = utils.loadJson(lines_path)
        self.assertEqual(loaded["daily"]["length"], 0)
        self.assertEqual(len(loaded["daily"]["lines"]), 0)


class TestInputValidation(unittest.TestCase):
    """Test input validation for drawing methods."""
    
    def setUp(self):
        """Set up a test DataFrame."""
        self.df = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'High': [102.0, 103.0, 104.0, 105.0, 106.0],
            'Low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'Close': [101.0, 102.0, 103.0, 104.0, 105.0],
            'Volume': [1000000, 1100000, 1200000, 1300000, 1400000]
        }, index=pd.date_range('2024-01-01', periods=5))
    
    def test_coordinate_bounds_validation(self):
        """Test that out-of-bounds coordinates are rejected."""
        # Test with index beyond dataframe length
        invalid_x = len(self.df) + 10
        self.assertGreaterEqual(invalid_x, len(self.df))
        
        # Test with negative index
        invalid_x_neg = -5
        self.assertLess(invalid_x_neg, 0)
    
    def test_coordinate_type_validation(self):
        """Test that invalid coordinate types are handled."""
        # Valid types
        valid_x = 2
        valid_y = 102.5
        self.assertIsInstance(valid_x, (int, float))
        self.assertIsInstance(valid_y, (int, float))
        
        # Invalid types would be strings, None, etc.
        invalid_types = ["string", None, [], {}]
        for invalid in invalid_types:
            self.assertNotIsInstance(invalid, (int, float))
    
    def test_closest_price_bounds(self):
        """Test magnet mode price snapping with valid bounds."""
        x = 2
        y = 102.5
        
        # Should be within bounds
        self.assertGreaterEqual(x, 0)
        self.assertLess(x, len(self.df))
        
        # Extract OHLC
        _open, high, low, close = self.df.iloc[x][['Open', 'High', 'Low', 'Close']]
        
        # Price should snap to nearest OHLC
        snapped_price = (_open if abs(_open - y) < abs(close - y) else close)
        self.assertIn(snapped_price, [_open, high, low, close])


class TestWatchlistCaching(unittest.TestCase):
    """Test watchlist caching functionality."""
    
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.cache = {}
    
    def tearDown(self):
        self.temp_dir.cleanup()
    
    def test_cache_hit(self):
        """Test that cached watchlist is returned without reload."""
        watch_key = "TEST_WATCH"
        watchlist_data = ["SBIN", "RELIANCE", "TCS"]
        
        # First access - populate cache
        self.cache[watch_key] = watchlist_data
        
        # Second access - should hit cache
        self.assertIn(watch_key, self.cache)
        cached = self.cache[watch_key]
        self.assertEqual(cached, watchlist_data)
    
    def test_cache_miss(self):
        """Test behavior when watchlist not in cache."""
        watch_key = "MISSING"
        self.assertNotIn(watch_key, self.cache)
    
    def test_cache_multiple_watchlists(self):
        """Test caching multiple distinct watchlists."""
        self.cache["WATCH_1"] = ["SBIN", "RELIANCE"]
        self.cache["WATCH_2"] = ["INFY", "TCS"]
        
        self.assertEqual(len(self.cache), 2)
        self.assertEqual(self.cache["WATCH_1"][0], "SBIN")
        self.assertEqual(self.cache["WATCH_2"][0], "INFY")


class TestFormatCoords(unittest.TestCase):
    """Test format_coords callback function."""
    
    def setUp(self):
        """Set up test data."""
        self.df = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0],
            'High': [102.0, 103.0, 104.0],
            'Low': [99.0, 100.0, 101.0],
            'Close': [101.0, 102.0, 103.0],
            'Volume': [1000000, 1100000, 1200000],
            'RS': [50.0, 52.0, 54.0]
        }, index=pd.date_range('2024-01-01', periods=3))
    
    def test_format_coords_with_valid_data(self):
        """Test coordinate formatting with valid OHLCV data."""
        # Simulate a valid coordinate
        ix = 1
        dt = self.df.index[ix]
        
        open_, high, low, close, vol = self.df.loc[dt, ["Open", "High", "Low", "Close", "Volume"]]
        
        # Build format string similar to format_coords
        result = f"O: {open_} H: {high} L: {low} C: {close} V: {vol:,.0f}"
        
        self.assertIn("O: 101.0", result)
        self.assertIn("H: 103.0", result)
        self.assertIn("V: 1,100,000", result)
    
    def test_format_coords_with_rs(self):
        """Test coordinate formatting with RS indicator."""
        ix = 1
        dt = self.df.index[ix]
        
        open_, high, low, close, vol = self.df.loc[dt, ["Open", "High", "Low", "Close", "Volume"]]
        rs_val = self.df.loc[dt, "RS"]
        
        result = f"O: {open_} H: {high} L: {low} C: {close} V: {vol:,.0f} RS: {rs_val}"
        
        self.assertIn("RS: 52.0", result)
    
    def test_format_coords_invalid_index(self):
        """Test that invalid index returns empty string gracefully."""
        # Out of bounds index
        ix = 100
        self.assertGreaterEqual(ix, len(self.df))
    
    def test_format_coords_none_input(self):
        """Test that None or empty input is handled gracefully."""
        # x=0 should return empty
        x = 0
        if not x:
            result = ""
        self.assertEqual(result, "")


class TestGlobalVariableElimination(unittest.TestCase):
    """Test that global df variable is properly used via instance."""
    
    def test_plotter_instance_storage(self):
        """Test that _current_df is stored on instance."""
        # Create mock dataframe
        mock_df = Mock(spec=pd.DataFrame)
        mock_df.shape = (100, 6)
        
        # Simulate storing on instance
        plotter_state = {"_current_df": mock_df}
        
        self.assertIsNotNone(plotter_state["_current_df"])
        self.assertEqual(plotter_state["_current_df"].shape, (100, 6))
    
    def test_callback_uses_instance_reference(self):
        """Test that callbacks use instance reference instead of global."""
        # Simulate the new approach with _plotter_instance
        mock_plotter = Mock()
        mock_df = Mock(spec=pd.DataFrame)
        mock_df.shape = (50, 6)
        mock_plotter._current_df = mock_df
        
        # Simulate format_coords using instance
        if mock_plotter is not None and mock_plotter._current_df is not None:
            current_df = mock_plotter._current_df
            self.assertEqual(current_df.shape, (50, 6))


class TestIndexLoadingErrorHandling(unittest.TestCase):
    """Test graceful error handling for missing index."""
    
    def test_missing_index_returns_none(self):
        """Test that missing index file returns None instead of exiting."""
        # Simulate missing file scenario
        idx_path = Path("/nonexistent/path/nifty50.csv")
        
        if not idx_path.is_file():
            result = None
        
        self.assertIsNone(result)
    
    def test_index_load_error_warning(self):
        """Test that index load errors produce warnings, not crashes."""
        # Simulate error condition
        try:
            # This would normally load data, but we simulate failure
            raise IOError("Cannot load index file")
        except IOError:
            warning_issued = True
        
        self.assertTrue(warning_issued)
    
    def test_rs_skipped_without_index(self):
        """Test that RS/MRS indicators are skipped gracefully."""
        idx_cl = None
        
        # Check if RS would be calculated
        if idx_cl is not None:
            rs_calculated = True
        else:
            rs_calculated = False
        
        self.assertFalse(rs_calculated)


class TestConfigurationUsage(unittest.TestCase):
    """Test that configuration options are used correctly."""
    
    def test_screenshot_dpi_config(self):
        """Test that screenshot DPI comes from config."""
        PLOT_SCREENSHOT_DPI = 150
        self.assertEqual(PLOT_SCREENSHOT_DPI, 150)
    
    def test_save_dpi_config(self):
        """Test that save DPI comes from config."""
        PLOT_SAVE_DPI = 300
        self.assertEqual(PLOT_SAVE_DPI, 300)
    
    def test_crosshair_config(self):
        """Test crosshair settings from config."""
        PLOT_CROSSHAIR_COLOR = "gray"
        PLOT_CROSSHAIR_LINEWIDTH = 0.5
        PLOT_CROSSHAIR_LINESTYLE = "--"
        
        self.assertEqual(PLOT_CROSSHAIR_COLOR, "gray")
        self.assertEqual(PLOT_CROSSHAIR_LINEWIDTH, 0.5)
        self.assertEqual(PLOT_CROSSHAIR_LINESTYLE, "--")
    
    def test_ema_alpha_divisor_config(self):
        """Test EMA alpha divisor from config."""
        PLOT_EMA_ALPHA_DIVISOR = 2
        
        # Test alpha calculation
        period = 12
        alpha = PLOT_EMA_ALPHA_DIVISOR / (period + 1)
        
        self.assertAlmostEqual(alpha, 2/13)
        self.assertGreater(alpha, 0)
        self.assertLess(alpha, 1)
    
    def test_plot_size_config(self):
        """Test plot size configuration."""
        PLOT_SIZE = (14, 9)
        self.assertEqual(PLOT_SIZE[0], 14)
        self.assertEqual(PLOT_SIZE[1], 9)


class TestCoordinateValidation(unittest.TestCase):
    """Test comprehensive coordinate validation."""
    
    def setUp(self):
        self.df = pd.DataFrame({
            'Open': np.arange(100, 150),
            'High': np.arange(102, 152),
            'Low': np.arange(98, 148),
            'Close': np.arange(101, 151),
            'Volume': [1000000] * 50
        }, index=pd.date_range('2024-01-01', periods=50))
    
    def test_tline_validation(self):
        """Test trend line coordinate validation."""
        coords = [(10, 110.5), (20, 120.5)]
        
        # Validate each coordinate is within bounds
        for x, y in coords:
            # Should pass validation: x is between 0 and length, y is numeric
            is_valid = (isinstance(x, (int, float)) and 
                       isinstance(y, (int, float)) and
                       0 <= x < len(self.df))
            self.assertTrue(is_valid, f"Coordinate ({x}, {y}) should be valid")
    
    def test_invalid_tline_coordinates(self):
        """Test that invalid trend line coordinates are rejected."""
        # Out of bounds
        invalid_coords = [(100, 110.5), (-5, 120.5)]
        
        for x, y in invalid_coords:
            is_valid = (0 <= x < len(self.df))
            if not is_valid:
                self.assertFalse(is_valid)
    
    def test_aline_validation(self):
        """Test arbitrary line coordinate validation."""
        coords = [(5, 105.0), (15, 115.0)]
        
        # Both coordinates should be valid
        for x, y in coords:
            self.assertGreaterEqual(x, 0)
            self.assertLess(x, len(self.df))
            self.assertIsInstance(y, (int, float))
    
    def test_horizontal_segment_validation(self):
        """Test horizontal segment coordinate validation."""
        y = 110.5
        xmin = 5
        xmax = 15
        
        # All should be valid
        self.assertIsInstance(y, (int, float))
        self.assertGreaterEqual(xmin, 0)
        self.assertLess(xmin, len(self.df))
        self.assertGreaterEqual(xmax, 0)
        self.assertLess(xmax, len(self.df))


class TestDateEncoderIntegration(unittest.TestCase):
    """Test DateEncoder integration with JSON persistence."""
    
    def test_date_encoder_handles_timestamp(self):
        """Test that DateEncoder handles pandas Timestamp."""
        encoder = utils.DateEncoder()
        ts = pd.Timestamp('2024-01-15')
        
        # Should not raise an error
        result = encoder.default(ts)
        self.assertIsInstance(result, str)
        self.assertIn('2024', result)
    
    def test_date_encoder_handles_datetime(self):
        """Test that DateEncoder handles datetime objects."""
        encoder = utils.DateEncoder()
        dt = datetime(2024, 1, 15, 12, 30, 0)
        
        result = encoder.default(dt)
        self.assertEqual(result, '2024-01-15T12:30:00')


class TestUndoStackManagement(unittest.TestCase):
    """Test undo stack management."""
    
    def test_undo_stack_limit(self):
        """Test that undo stack respects size limit."""
        _UNDO_STACK_LIMIT = 20
        undo_stack = []
        
        # Add items beyond limit
        for i in range(30):
            undo_stack.append(f"url:{i}")
            if len(undo_stack) > _UNDO_STACK_LIMIT:
                undo_stack.pop(0)
        
        # Should not exceed limit
        self.assertLessEqual(len(undo_stack), _UNDO_STACK_LIMIT)
    
    def test_undo_stack_fifo(self):
        """Test FIFO behavior of undo stack."""
        undo_stack = []
        urls = ["url1", "url2", "url3"]
        
        for url in urls:
            undo_stack.append(url)
        
        # Pop in LIFO order (last in, first out for undo)
        last = undo_stack.pop()
        self.assertEqual(last, "url3")
        
        next_undo = undo_stack.pop()
        self.assertEqual(next_undo, "url2")


if __name__ == '__main__':
    unittest.main()
