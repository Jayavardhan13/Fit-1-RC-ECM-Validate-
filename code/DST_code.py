"""
DST-based 1-RC parameter identification
Cell dataset: CALCE INR 18650-20R, SP20-2 DST, 25 degC

DIRECTORY SETUP
---------------
Put this Python file (for example, 1.py) in the SAME folder as:
    SP2_25C_DST.zip

The ZIP should contain the 50% SOC and 80% SOC DST Excel files.
The script extracts the ZIP automatically.

INSTALL ONCE:
    pip install numpy pandas matplotlib scipy xlrd openpyxl

RUN:
    python 1.py

IMPORTANT SCIENTIFIC NOTE
-------------------------
The capacity and OCV-SOC values entered below were obtained from SP20-1,
while the DST files are named SP20-2. This script uses them as an initial
approximation so that the workflow can be tested. Confirm with your TA
whether these files are intended to be combined. For final defensible
parameters, capacity and OCV data should ideally correspond to the same cell.

CALCE current sign convention in these files:
    Current(A) > 0 : charging
    Current(A) < 0 : discharging

The model uses discharge-positive current:
    I_dis = -I_CALCE

Only Step_Index == 7 is used for the DST dynamic profile, based on the
structure of the supplied DST files. The full Test_Time(s) column is used
and shifted so the Step 7 plot starts at t = 0 s.
"""

from pathlib import Path
import zipfile
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import least_squares


# ============================================================
# 1. USER SETTINGS
# ============================================================

# This automatically finds the folder containing this .py file.
BASE_DIR = Path(__file__).resolve().parent

# Keep the ZIP file in the same folder as this Python file.
DST_ZIP = BASE_DIR / "SP2_25C_DST.zip"

# Folders created automatically by this script.
EXTRACT_DIR = BASE_DIR / "DST_extracted"
OUTPUT_DIR = BASE_DIR / "DST_1RC_results"

# Capacity measured in the separate capacity test.
# NOTE: Capacity file was SP20-1; DST files are SP20-2.
Q_N_AH = 2.00895

# Initial SOC of the Step 7 DST profile.
INITIAL_SOC = {
    "50": 50.0,
    "80": 80.0,
}

# The OCV-SOC data below are the discharge OCV points previously calculated
# from the SP20-1 incremental-current OCV experiment.
# SOC must be in ascending order.
OCV_SOC_PERCENT = np.array([
    1.08, 10.42, 20.37, 30.32, 40.28, 50.23,
    60.19, 70.14, 80.09, 90.05, 100.00
], dtype=float)

OCV_VOLTAGE = np.array([
    3.2641, 3.4677, 3.5557, 3.5995, 3.6259, 3.6647,
    3.7536, 3.8399, 3.9401, 4.0503, 4.1758
], dtype=float)

# DST dynamic profile step identified in the supplied files.
DST_STEP_INDEX = 7

# If True, fit all Step 7 data points. This is recommended initially.
# If optimization is too slow, set FIT_EVERY_NTH_SAMPLE = 2 or 5.
FIT_EVERY_NTH_SAMPLE = 1


# ============================================================
# 2. CHECK FOLDERS AND EXTRACT THE ZIP
# ============================================================

def prepare_folders_and_extract():
    print("\nPROJECT FOLDER:")
    print(BASE_DIR)

    OUTPUT_DIR.mkdir(exist_ok=True)

    if not DST_ZIP.exists():
        possible_zips = list(BASE_DIR.glob("*.zip"))
        msg = (
            f"\nCannot find the expected ZIP file:\n{DST_ZIP}\n\n"
            "Make sure the DST ZIP file is in the same folder as this "
            "Python script and is named SP2_25C_DST.zip.\n"
            f"ZIP files currently found: {[p.name for p in possible_zips]}"
        )
        raise FileNotFoundError(msg)

    EXTRACT_DIR.mkdir(exist_ok=True)

    with zipfile.ZipFile(DST_ZIP, "r") as zf:
        zf.extractall(EXTRACT_DIR)

    print("\nDST ZIP extracted to:")
    print(EXTRACT_DIR)


# ============================================================
# 3. FIND AND LOAD 50% AND 80% SOC DST FILES
# ============================================================

def find_dst_excel_file(soc_label):
    candidates = []
    for pattern in (f"*{soc_label}SOC*.xls", f"*{soc_label}SOC*.xlsx"):
        candidates.extend(EXTRACT_DIR.rglob(pattern))

    if not candidates:
        raise FileNotFoundError(
            f"Could not find an Excel DST file containing "
            f"'{soc_label}SOC' inside {EXTRACT_DIR}."
        )

    # Prefer the first matching file.
    return candidates[0]


def load_dst_step(soc_label):
    file_path = find_dst_excel_file(soc_label)

    print(f"\nLoading {soc_label}% SOC file:")
    print(file_path.name)

    # The uploaded CALCE DST files use the Channel_1-008 sheet.
    data = pd.read_excel(file_path, sheet_name="Channel_1-008")

    required_columns = [
        "Test_Time(s)", "Step_Index", "Current(A)", "Voltage(V)"
    ]
    missing = [c for c in required_columns if c not in data.columns]
    if missing:
        raise ValueError(
            f"Missing columns in {file_path.name}: {missing}\n"
            f"Available columns: {list(data.columns)}"
        )

    # Select only the dynamic DST profile.
    dst = data.loc[
        pd.to_numeric(data["Step_Index"], errors="coerce")
        == DST_STEP_INDEX
    ].copy()

    dst["Test_Time(s)"] = pd.to_numeric(
        dst["Test_Time(s)"], errors="coerce"
    )
    dst["Current(A)"] = pd.to_numeric(
        dst["Current(A)"], errors="coerce"
    )
    dst["Voltage(V)"] = pd.to_numeric(
        dst["Voltage(V)"], errors="coerce"
    )

    dst = dst.dropna(
        subset=["Test_Time(s)", "Current(A)", "Voltage(V)"]
    )
    dst = dst.sort_values("Test_Time(s)")
    dst = dst.drop_duplicates(
        subset=["Test_Time(s)"], keep="first"
    ).reset_index(drop=True)

    if len(dst) < 20:
        raise ValueError(
            f"Only {len(dst)} records found in Step {DST_STEP_INDEX} "
            f"for {soc_label}% SOC. Check the Step_Index selection."
        )

    # Use Test_Time(s), shifted to start at zero for plotting.
    absolute_time = dst["Test_Time(s)"].to_numpy(dtype=float)
    elapsed_time = absolute_time - absolute_time[0]

    if np.any(np.diff(elapsed_time) <= 0):
        raise ValueError(
            "Test_Time(s) must be strictly increasing within Step 7."
        )

    current_calce = dst["Current(A)"].to_numpy(dtype=float)
    voltage_measured = dst["Voltage(V)"].to_numpy(dtype=float)

    print(f"Step 7 data points: {len(dst)}")
    print(
        f"Elapsed time: {elapsed_time[0]:.3f} to "
        f"{elapsed_time[-1]:.3f} seconds"
    )
    print(
        f"Current range: {current_calce.min():.3f} to "
        f"{current_calce.max():.3f} A"
    )
    print(
        f"Voltage range: {voltage_measured.min():.3f} to "
        f"{voltage_measured.max():.3f} V"
    )

    return dst, elapsed_time, current_calce, voltage_measured


# ============================================================
# 4. COULOMB COUNTING: CALCE CURRENT TO SOC
# ============================================================

def calculate_soc(time_s, current_calce, initial_soc_percent):
    """
    CALCE convention:
        positive current = charging
        negative current = discharging

    Coulomb counting:
        SOC(t) = SOC_initial + integral(I_CALCE dt)/(3600*Qn)*100

    Trapezoidal integration is used between adjacent samples.
    """
    soc = np.zeros(len(time_s), dtype=float)
    soc[0] = initial_soc_percent

    for k in range(1, len(time_s)):
        dt = time_s[k] - time_s[k - 1]

        # Average current over this interval (A).
        i_average = 0.5 * (
            current_calce[k - 1] + current_calce[k]
        )

        # Positive CALCE current charges the cell and increases SOC.
        delta_soc = (
            i_average * dt / (3600.0 * Q_N_AH) * 100.0
        )

        soc[k] = soc[k - 1] + delta_soc

    return soc


# ============================================================
# 5. OCV LOOKUP FROM THE OCV-SOC CURVE
# ============================================================

def calculate_ocv_from_soc(soc_percent):
    """
    Linear interpolation between measured OCV-SOC points.
    Extrapolation is not allowed: it raises a warning and clamps
    to the nearest measured endpoint, because no measured OCV data
    are available outside the table.
    """
    if np.min(soc_percent) < OCV_SOC_PERCENT.min() or \
       np.max(soc_percent) > OCV_SOC_PERCENT.max():

        warnings.warn(
            "Calculated SOC goes outside the measured OCV-SOC table. "
            "The OCV lookup will be clamped at the nearest endpoint. "
            "Check initial SOC, current sign, capacity and dataset matching."
        )

    return np.interp(
        soc_percent,
        OCV_SOC_PERCENT,
        OCV_VOLTAGE
    )


# ============================================================
# 6. 1-RC BATTERY MODEL
# ============================================================

def simulate_1rc(parameters, time_s, current_calce, ocv):
    """
    Optimized parameters:
        R0       : ohmic resistance (ohm)
        R1       : polarization resistance (ohm)
        tau      : RC time constant (s)
        V1_init  : initial polarization voltage (V)

    C1 is calculated as:
        C1 = tau / R1

    CALCE current is positive for charge. The model equation is:
        Vterminal = OCV + I_CALCE*R0 - V1

    Polarization state equation in CALCE current convention:
        dV1/dt = -V1/tau - (R1/tau)*I_CALCE

    Equivalently, using discharge-positive current I_dis=-I_CALCE:
        Vterminal = OCV - I_dis*R0 - V1
        dV1/dt = -V1/tau + (R1/tau)*I_dis
    """
    r0, r1, tau, v1_initial = parameters

    v1 = np.zeros(len(time_s), dtype=float)
    v1[0] = v1_initial

    for k in range(1, len(time_s)):
        dt = time_s[k] - time_s[k - 1]

        # Use the average current over the interval.
        i_avg_calce = 0.5 * (
            current_calce[k - 1] + current_calce[k]
        )

        a = np.exp(-dt / tau)

        # CALCE current: positive = charge, negative = discharge.
        v1[k] = (
            a * v1[k - 1]
            - r1 * (1.0 - a) * i_avg_calce
        )

    # Terminal voltage using CALCE current sign convention.
    v_model = ocv + current_calce * r0 - v1

    return v_model, v1


# ============================================================
# 7. IDENTIFY R0, R1 AND C1 USING LEAST-SQUARES FITTING
# ============================================================

def identify_1rc_parameters(
    time_s, current_calce, voltage_measured, ocv
):
    """
    Fit R0, R1, tau and initial polarization voltage.
    Then calculate C1 = tau/R1.

    Bounds are broad positive physical bounds, not predetermined
    battery parameter values.
    """

    # Optimization variables are log10(R0), log10(R1), log10(tau), V1_init.
    # Log parameters guarantee positive R0, R1 and tau.
    initial_guess = np.array([
        np.log10(0.03),   # R0 = 0.03 ohm initial guess
        np.log10(0.02),   # R1 = 0.02 ohm initial guess
        np.log10(100.0),  # tau = 100 s initial guess
        0.0               # initial polarization voltage
    ])

    lower_bounds = np.array([
        np.log10(1e-5),
        np.log10(1e-5),
        np.log10(0.05),
        -1.0
    ])

    upper_bounds = np.array([
        np.log10(0.5),
        np.log10(0.5),
        np.log10(10000.0),
        1.0
    ])

    # Optional downsampling for optimization speed.
    idx = np.arange(0, len(time_s), FIT_EVERY_NTH_SAMPLE)
    if idx[-1] != len(time_s) - 1:
        idx = np.append(idx, len(time_s) - 1)

    t_fit = time_s[idx]
    i_fit = current_calce[idx]
    v_fit = voltage_measured[idx]
    ocv_fit = ocv[idx]

    def residual_function(x):
        r0 = 10.0 ** x[0]
        r1 = 10.0 ** x[1]
        tau = 10.0 ** x[2]
        v1_initial = x[3]

        p = [r0, r1, tau, v1_initial]
        v_predicted, _ = simulate_1rc(
            p, t_fit, i_fit, ocv_fit
        )
        return v_predicted - v_fit

    print("\nStarting nonlinear least-squares parameter fitting...")
    result = least_squares(
        residual_function,
        x0=initial_guess,
        bounds=(lower_bounds, upper_bounds),
        loss="soft_l1",
        f_scale=0.01,
        max_nfev=3000,
        verbose=0
    )

    r0 = 10.0 ** result.x[0]
    r1 = 10.0 ** result.x[1]
    tau = 10.0 ** result.x[2]
    v1_initial = result.x[3]
    c1 = tau / r1

    parameters = [r0, r1, tau, v1_initial]

    # Simulate using all original samples for final output.
    v_predicted, v1 = simulate_1rc(
        parameters, time_s, current_calce, ocv
    )

    error = voltage_measured - v_predicted

    rmse = np.sqrt(np.mean(error ** 2))
    mae = np.mean(np.abs(error))
    max_abs_error = np.max(np.abs(error))

    metrics = {
        "RMSE_V": rmse,
        "MAE_V": mae,
        "Max_Absolute_Error_V": max_abs_error,
        "Optimization_Success": result.success,
        "Optimization_Message": result.message
    }

    fitted = {
        "R0_ohm": r0,
        "R1_ohm": r1,
        "C1_F": c1,
        "Tau_s": tau,
        "Initial_Polarization_V": v1_initial
    }

    return fitted, v_predicted, v1, metrics


# ============================================================
# 8. PLOTS
# ============================================================

def plot_dst_current_voltage(soc_label, time_s, current, voltage):
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True
    )
    fig.patch.set_facecolor("white")

    ax1.set_facecolor("white")
    ax1.plot(time_s, current, color="blue", linewidth=0.8)
    ax1.set_ylabel("Current (A)")
    ax1.set_title(f"DST Current Profile — {soc_label}% SOC")
    ax1.grid(True, alpha=0.3)

    ax2.set_facecolor("white")
    ax2.plot(time_s, voltage, color="red", linewidth=0.8)
    ax2.set_ylabel("Terminal Voltage (V)")
    ax2.set_xlabel("Elapsed DST Time (s)")
    ax2.set_title(f"Measured Battery Voltage — {soc_label}% SOC")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(
        OUTPUT_DIR / f"DST_{soc_label}SOC_Current_Voltage.png",
        dpi=300, facecolor="white"
    )
    plt.show()


def plot_soc_ocv(soc_label, time_s, soc, ocv):
    fig, ax = plt.subplots(figsize=(12, 4.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(time_s, soc, label="Calculated SOC", color="blue")
    ax.set_xlabel("Elapsed DST Time (s)")
    ax.set_ylabel("SOC (%)")
    ax.set_title(f"Calculated SOC During DST — {soc_label}% SOC")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        OUTPUT_DIR / f"DST_{soc_label}SOC_SOC_vs_Time.png",
        dpi=300, facecolor="white"
    )
    plt.show()

    fig, ax = plt.subplots(figsize=(12, 4.5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(time_s, ocv, label="OCV from lookup table", color="green")
    ax.set_xlabel("Elapsed DST Time (s)")
    ax.set_ylabel("OCV (V)")
    ax.set_title(f"Lookup OCV During DST — {soc_label}% SOC")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        OUTPUT_DIR / f"DST_{soc_label}SOC_OCV_vs_Time.png",
        dpi=300, facecolor="white"
    )
    plt.show()


def plot_voltage_fit(soc_label, time_s, measured, predicted):
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.plot(
        time_s, measured,
        label="Measured voltage",
        color="black", linewidth=0.9
    )
    ax.plot(
        time_s, predicted,
        label="1-RC predicted voltage",
        color="red", linewidth=0.9, alpha=0.85
    )

    ax.set_xlabel("Elapsed DST Time (s)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title(f"Measured vs Predicted Voltage — {soc_label}% SOC")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(
        OUTPUT_DIR / f"DST_{soc_label}SOC_Measured_vs_Predicted.png",
        dpi=300, facecolor="white"
    )
    plt.show()

    error = measured - predicted
    fig, ax = plt.subplots(figsize=(12, 4))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(time_s, error, color="purple", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Elapsed DST Time (s)")
    ax.set_ylabel("Voltage Error (V)")
    ax.set_title(f"Voltage Prediction Error — {soc_label}% SOC")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(
        OUTPUT_DIR / f"DST_{soc_label}SOC_Voltage_Error.png",
        dpi=300, facecolor="white"
    )
    plt.show()


# ============================================================
# 9. MAIN PROGRAM: RUN 50% AND 80% SOC
# ============================================================

def main():
    print("=" * 65)
    print("CALCE INR 18650-20R — DST 1-RC PARAMETER IDENTIFICATION")
    print("=" * 65)

    prepare_folders_and_extract()

    all_summaries = []

    for soc_label in ["50", "80"]:

        print("\n" + "=" * 65)
        print(f"PROCESSING DST AT {soc_label}% SOC")
        print("=" * 65)

        # Load Step 7 dynamic profile.
        dst, time_s, current_calce, voltage_measured = load_dst_step(
            soc_label
        )

        # Plot raw experimental current and voltage.
        plot_dst_current_voltage(
            soc_label, time_s, current_calce, voltage_measured
        )

        # Calculate SOC using the CALCE current convention.
        soc = calculate_soc(
            time_s,
            current_calce,
            INITIAL_SOC[soc_label]
        )

        print(
            f"\nCalculated SOC range: {soc.min():.3f}% "
            f"to {soc.max():.3f}%"
        )

        # Calculate OCV at every time point using the OCV-SOC table.
        ocv = calculate_ocv_from_soc(soc)

        # Plot calculated SOC and lookup OCV.
        plot_soc_ocv(soc_label, time_s, soc, ocv)

        # Fit R0, R1 and C1 using the complete DST profile.
        fitted, voltage_predicted, v1, metrics = identify_1rc_parameters(
            time_s,
            current_calce,
            voltage_measured,
            ocv
        )

        # Plot model fitting and voltage error.
        plot_voltage_fit(
            soc_label,
            time_s,
            voltage_measured,
            voltage_predicted
        )

        # Print final estimated parameters.
        print("\nIDENTIFIED 1-RC PARAMETERS")
        print("-" * 45)
        for key, value in fitted.items():
            print(f"{key:30s}: {value:.8g}")

        print("\nMODEL FIT METRICS")
        print("-" * 45)
        for key, value in metrics.items():
            print(f"{key:30s}: {value}")

        # Save time-series output to CSV.
        result_df = pd.DataFrame({
            "Test_Time(s)": dst["Test_Time(s)"].to_numpy(),
            "Elapsed_DST_Time(s)": time_s,
            "Step_Index": dst["Step_Index"].to_numpy(),
            "Current_CALCE(A)": current_calce,
            "Voltage_Measured(V)": voltage_measured,
            "SOC_Calculated(%)": soc,
            "OCV_Lookup(V)": ocv,
            "Polarization_Voltage(V)": v1,
            "Voltage_1RC_Predicted(V)": voltage_predicted,
            "Voltage_Error(V)": voltage_measured - voltage_predicted
        })

        csv_path = OUTPUT_DIR / f"DST_{soc_label}SOC_1RC_TimeSeries.csv"
        result_df.to_csv(csv_path, index=False)

        summary_row = {
            "Initial_SOC_percent": float(soc_label),
            **fitted,
            **metrics
        }
        all_summaries.append(summary_row)

    # Save combined parameter summary.
    summary_df = pd.DataFrame(all_summaries)
    summary_path = OUTPUT_DIR / "DST_1RC_Parameter_Summary.csv"
    summary_df.to_csv(summary_path, index=False)

    print("\n" + "=" * 65)
    print("FINAL 1-RC PARAMETER SUMMARY")
    print("=" * 65)
    print(summary_df.to_string(index=False))

    print("\nAll plots and CSV files saved in:")
    print(OUTPUT_DIR.resolve())

    print("\nIMPORTANT:")
    print(
        "These are preliminary estimates because the entered capacity "
        "and OCV curve are from SP20-1, whereas the DST files are SP20-2. "
        "Confirm dataset compatibility with your TA before reporting "
        "the fitted parameters as final."
    )


if __name__ == "__main__":
    main()
