import logging
import re
import subprocess
from pathlib import Path

import pytest

import dicomfix.main

logger = logging.getLogger(__name__)


input_files = {
    'plan': Path('res', 'Plan5.5.dcm'),
    'scale_factors.dat': Path('res', 'scale_factors.dat'),
    'scale_factors3.dat': Path('res', 'scale_factors3.dat')
}


def test_call_cmd_inspect():
    """Test calling dicomfix to inspect an input DICOM file."""
    fn = str(input_files['plan'])
    with pytest.raises(SystemExit) as e:
        dicomfix.main.main([fn, '-i'])
        logger.info(f"Catching SystemExit with code: {str(e.value):s}")
        assert e.value.code == 0

    logger.info(f"Catching SystemExit with code: {str(e.value):s}")
    assert e.value.code == 0


def test_tr4wiz(tmp_path):
    fn = str(input_files['plan'])
    output_file = tmp_path / "output.dcm"
    dicomfix.main.main([fn, '-tr4',  '-o', str(output_file)])
    expected_file = output_file
    assert expected_file.is_file()
    assert expected_file.stat().st_size > 0


def test_rescale(caplog, tmp_path):
    fn = str(input_files['plan'])
    output_file = tmp_path / "output.dcm"

    caplog.set_level(logging.INFO, logger="dicomfix.dicomutil")

    # Run the rescale command
    dicomfix.main.main([fn, '-rf=2.0', '-o', str(output_file)])

    # Run the inspect command on the output file and capture the output
    result = subprocess.run(
        ["python", "-m", "dicomfix.main", str(output_file), "-i"],
        capture_output=True,
        text=True,
        check=True,
    )

    # Check the output for the expected values
    output = result.stdout
    assert "Beam Meterset            : 76867.92 MU" in output, \
        f"Expected 'Beam Meterset            : 76867.92 MU' in output, got:\n{output}"
    assert "Beam Dose                : 11.00 Gy(RBE)" in output, \
        f"Expected 'Beam Dose                : 11.00 Gy(RBE)' in output, got:\n{output}"

    # Optionally, check the log for the expected values
    found = any(
        ("Beam Dose" in rec.getMessage() and "5.50" in rec.getMessage() and "11.00" in rec.getMessage())
        for rec in caplog.records
        if rec.name.startswith("dicomfix.dicomutil") and rec.levelno >= logging.INFO
    )
    assert found, 'No log line contains all of "Beam Dose", "5.50", and "11.00"'

    assert output_file.is_file()
    assert output_file.stat().st_size > 0


def extract_coefficients(log_output):
    pattern = r"Layer\s+(\d{2})\s+(\d+\.\d{3})\s+(\d+\.\d{3})"
    matches = re.findall(pattern, log_output)
    return [(int(layer), float(original), float(new)) for layer, original, new in matches]


def test_rescale_with_scale_factors(caplog, tmp_path):
    fn = str(input_files['plan'])
    scale_factors_file = str(input_files['scale_factors3.dat'])
    output_file = tmp_path / "output.dcm"

    caplog.set_level(logging.INFO, logger="dicomfix.dicomutil")

    # Run the rescale command with scale factors
    dicomfix.main.main([fn, '-w', scale_factors_file, '-o', str(output_file)])

    # Run the inspect command on the output file and capture the output
    result = subprocess.run(
        ["python", "-m", "dicomfix.main", str(output_file), "-i", "-v"],
        capture_output=True,
        text=True,
        check=True,
    )

    # Check the output for the expected values
    output = result.stdout

    # Expected values based on the log output you provided
    expected_values = [
        ("Final Cumulative Meterset Weight : 6300.80", None),
        ("Beam Meterset            : 38433.96 MU", None),
        ("Beam Dose                : 5.50 Gy(RBE)", None),
        ("Cumulative Meterset Weight       : 0.00", "Energy Layer # 01"),
        ("Cumulative Meterset Weight       : 2771.96", "Energy Layer # 02"),
        ("Cumulative Meterset Weight       : 3744.82", "Energy Layer # 03"),
        ("Cumulative Meterset Weight       : 4432.00", "Energy Layer # 04"),
        ("Cumulative Meterset Weight       : 4977.41", "Energy Layer # 05"),
        ("Cumulative Meterset Weight       : 5400.61", "Energy Layer # 06"),
        ("Cumulative Meterset Weight       : 5753.09", "Energy Layer # 07"),
        ("Cumulative Meterset Weight       : 6037.25", "Energy Layer # 08"),
    ]

    # Check each expected value in the output
    for expected_value, context in expected_values:
        assert expected_value in output, f"Expected '{expected_value}' in the context of '{context}' in output, got:\n{output}"

    # Check the log for the expected scale factors
    found_scale_factors = [
        ("Reduce cumulative weight in layer 0 by factor: 1.0000" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 1 by factor: 0.8719" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 2 by factor: 0.8516" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 3 by factor: 0.8377" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 4 by factor: 0.8165" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 5 by factor: 0.8093" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 6 by factor: 0.7931" in rec.getMessage()) or
        ("Reduce cumulative weight in layer 7 by factor: 0.7884" in rec.getMessage())
        for rec in caplog.records if rec.name.startswith("dicomfix.dicomutil") and rec.levelno >= logging.INFO
    ]
    assert any(found_scale_factors), 'No log line contains the expected scale factors'

    # Extract log messages
    log_output = "\n".join(rec.getMessage() for rec in caplog.records if rec.name.startswith("dicomfix.dicomutil"))

    # Expected CumulativeDoseReferenceCoefficient values
    expected_coefficients = [
        (0, 0.000, 0.000),
        (1, 0.396, 0.440),
        (2, 0.396, 0.440),
        (3, 0.556, 0.594),
        (4, 0.556, 0.594),
        (5, 0.671, 0.703),
        (6, 0.671, 0.703),
        (7, 0.765, 0.790),
        (8, 0.765, 0.790),
        (9, 0.839, 0.857),
        (10, 0.839, 0.857),
        (11, 0.901, 0.913),
        (12, 0.901, 0.913),
        (13, 0.952, 0.958),
        (14, 0.952, 0.958),
        (15, 1.000, 1.000),
    ]

    # Extract coefficients from log
    coefficients = extract_coefficients(log_output)

    # Debug: Print extracted coefficients
    print("Extracted coefficients:", coefficients)

    # Check each expected coefficient strictly
    for i, (expected_layer, expected_original, expected_new) in enumerate(expected_coefficients):
        layer, original, new = coefficients[i]
        assert layer == expected_layer, f"Layer mismatch at index {i}: Expected {expected_layer}, got {layer}"
        assert abs(
            original - expected_original) < 1e-3, \
            f"Original coefficient mismatch at Layer {expected_layer:02}: Expected {expected_original}, got {original}"
        assert abs(
            new - expected_new) < 1e-3, \
            f"New coefficient mismatch at Layer {expected_layer:02}: Expected {expected_new}, got {new}"

    assert output_file.is_file()
    assert output_file.stat().st_size > 0
