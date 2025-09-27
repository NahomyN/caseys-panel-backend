"""Test export daily stats script functionality."""
import sys
import json
import subprocess
from datetime import date
from io import StringIO
from app.services.database import SessionLocal
from app.services.models import DailyRunStats


def test_export_daily_stats_script():
    """Test that export script works and outputs JSON."""
    db = SessionLocal()
    
    try:
        # Create some test data
        test_date = "2024-01-15"
        
        # Clean up existing data for this date
        db.query(DailyRunStats).filter_by(date=test_date).delete()
        
        # Create test stats
        test_stat = DailyRunStats(
            date=test_date,
            runs_started=10,
            runs_completed=8,
            avg_total_duration_ms=1500,
            failures=2,
            fallbacks_used=1
        )
        db.add(test_stat)
        db.commit()
        
        # Import and run the main function directly
        from tools.export_daily_stats import main
        
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            result_count = main()
            output = captured_output.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Verify the output
        assert result_count >= 1, "Should export at least one record"
        
        # Parse JSON output
        stats_data = json.loads(output)
        assert isinstance(stats_data, list), "Output should be JSON list"
        assert len(stats_data) >= 1, "Should have at least one stats record"
        
        # Find our test record
        test_record = None
        for record in stats_data:
            if record["date"] == test_date:
                test_record = record
                break
        
        assert test_record is not None, "Should find our test record"
        assert test_record["runs_started"] == 10
        assert test_record["runs_completed"] == 8
        assert test_record["avg_total_duration_ms"] == 1500
        assert test_record["failures"] == 2
        assert test_record["fallbacks_used"] == 1
        
        print(f"✅ Export script works, exported {len(stats_data)} records")
        
    finally:
        # Cleanup
        db.query(DailyRunStats).filter_by(date=test_date).delete()
        db.commit()
        db.close()


def test_export_script_empty_database():
    """Test export script behavior with empty database."""
    db = SessionLocal()
    
    try:
        # Clear all daily stats
        db.query(DailyRunStats).delete()
        db.commit()
        
        # Import and run the main function
        from tools.export_daily_stats import main
        
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            result_count = main()
            output = captured_output.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Should return 0 for empty
        assert result_count == 0, "Should return 0 for empty database"
        
        # Should output empty JSON array
        stats_data = json.loads(output)
        assert stats_data == [], "Should output empty JSON array"
        
        print("✅ Export script handles empty database correctly")
        
    finally:
        db.close()


def test_export_script_json_format():
    """Test that export script outputs valid JSON with correct structure."""
    db = SessionLocal()
    
    try:
        # Create multiple test records
        test_dates = ["2024-01-01", "2024-01-02"]
        
        # Clean up
        for test_date in test_dates:
            db.query(DailyRunStats).filter_by(date=test_date).delete()
        
        # Create test data
        for i, test_date in enumerate(test_dates):
            stat = DailyRunStats(
                date=test_date,
                runs_started=5 + i,
                runs_completed=4 + i,
                avg_total_duration_ms=1000 + (i * 100),
                failures=1,
                fallbacks_used=0
            )
            db.add(stat)
        db.commit()
        
        # Run export
        from tools.export_daily_stats import main
        
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            result_count = main()
            output = captured_output.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Parse and validate JSON structure
        stats_data = json.loads(output)
        
        assert len(stats_data) >= 2, "Should have at least 2 records"
        
        # Check each record has required fields
        required_fields = ["date", "runs_started", "runs_completed", "avg_total_duration_ms", "failures", "fallbacks_used"]
        
        for record in stats_data:
            for field in required_fields:
                assert field in record, f"Missing field {field} in record"
            
            # Check data types
            assert isinstance(record["date"], str)
            assert isinstance(record["runs_started"], int)
            assert isinstance(record["runs_completed"], int)
            assert isinstance(record["failures"], int)
            assert isinstance(record["fallbacks_used"], int)
            # avg_total_duration_ms can be null
            if record["avg_total_duration_ms"] is not None:
                assert isinstance(record["avg_total_duration_ms"], int)
        
        print("✅ Export script outputs valid JSON with correct structure")
        
    finally:
        # Cleanup
        for test_date in test_dates:
            db.query(DailyRunStats).filter_by(date=test_date).delete()
        db.commit()
        db.close()


def test_export_script_ordering():
    """Test that export script outputs records in date order."""
    db = SessionLocal()
    
    try:
        # Create test data out of order
        test_dates = ["2024-01-03", "2024-01-01", "2024-01-02"]
        
        # Clean up
        for test_date in test_dates:
            db.query(DailyRunStats).filter_by(date=test_date).delete()
        
        # Add records in random order
        for test_date in test_dates:
            stat = DailyRunStats(
                date=test_date,
                runs_started=1,
                runs_completed=1,
                failures=0,
                fallbacks_used=0
            )
            db.add(stat)
        db.commit()
        
        # Export
        from tools.export_daily_stats import main
        
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            main()
            output = captured_output.getvalue()
        finally:
            sys.stdout = old_stdout
        
        stats_data = json.loads(output)
        
        # Extract dates and verify ordering
        exported_dates = [record["date"] for record in stats_data if record["date"] in test_dates]
        expected_order = ["2024-01-01", "2024-01-02", "2024-01-03"]
        
        # Should be in chronological order
        for i, date in enumerate(expected_order):
            assert date in exported_dates, f"Missing date {date}"
            assert exported_dates.index(date) == i, f"Date {date} not in correct position"
        
        print("✅ Export script outputs records in date order")
        
    finally:
        # Cleanup
        for test_date in test_dates:
            db.query(DailyRunStats).filter_by(date=test_date).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_export_daily_stats_script()
    test_export_script_empty_database()
    test_export_script_json_format()
    test_export_script_ordering()