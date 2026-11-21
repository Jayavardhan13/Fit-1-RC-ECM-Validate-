
# ================================================================
# FUDS VALIDATION OF 1-RC BATTERY MODEL
# CALCE INR 18650-20R | 25 deg C
#
# 50% FUDS -> 50% DST parameters
# 80% FUDS -> 80% DST parameters
#
# IMPORTANT:
# DST parameters are fixed.
# No parameter fitting is performed using FUDS data.
#
# CALCE current convention:
# Positive current = Charging
# Negative current = Discharging
# ================================================================

import os
import zipfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


# ================================================================
# 1. PROJECT FOLDER
# ================================================================

PROJECT_FOLDER = Path(__file__).resolve().parent

ZIP_FILE = PROJECT_FOLDER / "SP2_25C_FUDS.zip"

OUTPUT_FOLDER = PROJECT_FOLDER / "FUDS_1RC_validation_results"

OUTPUT_FOLDER.mkdir(exist_ok=True)


# ================================================================
# 2. BATTERY CAPACITY
# ================================================================

Q_N = 2.00895  # Ah


# ================================================================
# 3. OCV-SOC LOOKUP TABLE
# SAMPLE 1, 25 DEG C
# ================================================================

SOC_TABLE = np.array([
    1.08,
    10.42,
    20.37,
    30.32,
    40.28,
    50.23,
    60.19,
    70.14,
    80.09,
    90.05,
    100.00
])

OCV_TABLE = np.array([
    3.2641,
    3.4677,
    3.5557,
    3.5995,
    3.6259,
    3.6647,
    3.7536,
    3.8399,
    3.9401,
    4.0503,
    4.1758
])


# ================================================================
# 4. DST IDENTIFIED PARAMETERS
# THESE PARAMETERS ARE KEPT FIXED DURING FUDS VALIDATION
# ================================================================

DST_PARAMETERS = {

    50: {
        "R0": 0.07131505151879072,
        "R1": 0.01068749040712964,
        "C1": 965.0421556518509
    },

    80: {
        "R0": 0.07330536288719898,
        "R1": 0.01814249471932885,
        "C1": 1431.655203805654
    }
}


# ================================================================
# 5. FUDS FILE NAMES
# ================================================================

FUDS_FILES = {

    50: "11_09_2015_SP20-2_FUDS_50SOC.xls",

    80: "11_06_2015_SP20-2_FUDS_80SOC.xls"

}


# ================================================================
# 6. LOAD FUDS EXCEL DATA
# ================================================================

def load_fuds_data(initial_soc):

    filename = FUDS_FILES[initial_soc]

    # First check whether the Excel file is already extracted
    excel_path = PROJECT_FOLDER / filename

    if not excel_path.exists():

        if not ZIP_FILE.exists():
            raise FileNotFoundError(
                "FUDS ZIP file not found. "
                "Keep SP2_25C_FUDS.zip in the project folder."
            )

        print("Extracting:", filename)

        with zipfile.ZipFile(ZIP_FILE, "r") as zip_ref:

            if filename not in zip_ref.namelist():
                raise FileNotFoundError(
                    filename + " not found inside the ZIP file."
                )

            zip_ref.extract(filename, PROJECT_FOLDER)

    print("Loading:", filename)

    df = pd.read_excel(
        excel_path,
        sheet_name="Channel_1-008"
    )

    return df


# ================================================================
# 7. VALIDATE ONE FUDS EXPERIMENT
# ================================================================

def validate_fuds(initial_soc):

    print("\n" + "=" * 65)
    print("PROCESSING FUDS AT", initial_soc, "% SOC")
    print("=" * 65)

    # ------------------------------------------------------------
    # LOAD DATA
    # ------------------------------------------------------------

    df = load_fuds_data(initial_soc)

    # FUDS dynamic profile starts at Step_Index = 7
    data = df[df["Step_Index"] == 7].copy()

    data.reset_index(drop=True, inplace=True)

    if len(data) == 0:
        raise ValueError("No Step_Index 7 data found.")

    # ------------------------------------------------------------
    # EXTRACT EXPERIMENTAL DATA
    # ------------------------------------------------------------

    time_absolute = data["Test_Time(s)"].to_numpy(dtype=float)

    # Elapsed time starts from the beginning of FUDS Step 7
    time = time_absolute - time_absolute[0]

    current = data["Current(A)"].to_numpy(dtype=float)

    voltage_measured = data["Voltage(V)"].to_numpy(dtype=float)

    N = len(data)

    print("Number of data points:", N)

    print("FUDS duration:", time[-1], "seconds")

    print("Current range:",
          np.min(current), "to", np.max(current), "A")

    print("Voltage range:",
          np.min(voltage_measured),
          "to", np.max(voltage_measured), "V")


    # ============================================================
    # 8. CALCULATE SOC USING COULOMB COUNTING
    # ============================================================

    SOC = np.zeros(N)

    # Initial SOC = 50% or 80%
    SOC[0] = initial_soc

    for k in range(1, N):

        dt = time[k] - time[k - 1]

        # Trapezoidal current integration
        I_average = (current[k] + current[k - 1]) / 2.0

        # CALCE convention:
        # Positive current increases SOC
        # Negative current decreases SOC

        SOC[k] = SOC[k - 1] + (
            I_average * dt / (3600.0 * Q_N)
        ) * 100.0

    print("\nSOC calculated using Coulomb counting")

    print("Initial SOC:", SOC[0], "%")

    print("Final SOC:", SOC[-1], "%")

    print("Minimum SOC:", np.min(SOC), "%")


    # ============================================================
    # 9. CALCULATE OCV USING LINEAR INTERPOLATION
    # ============================================================

    OCV = np.interp(
        SOC,
        SOC_TABLE,
        OCV_TABLE
    )

    # Identify SOC values outside measured OCV table
    outside_range = (
        (SOC < SOC_TABLE[0]) |
        (SOC > SOC_TABLE[-1])
    )

    print("\nOCV calculated using linear interpolation")

    if np.any(outside_range):

        print("WARNING: SOC outside measured OCV-SOC range.")

        print("Number of affected samples:",
              np.sum(outside_range))

        print("np.interp clamps OCV to the nearest endpoint.")

    else:

        print("All SOC values are inside OCV table range.")


    # ============================================================
    # 10. LOAD FIXED DST PARAMETERS
    # ============================================================

    parameters = DST_PARAMETERS[initial_soc]

    R0 = parameters["R0"]

    R1 = parameters["R1"]

    C1 = parameters["C1"]

    tau = R1 * C1

    print("\nFIXED DST PARAMETERS")

    print("R0 =", R0, "Ohm")

    print("R1 =", R1, "Ohm")

    print("C1 =", C1, "F")

    print("Tau =", tau, "seconds")


    # ============================================================
    # 11. INITIAL POLARIZATION VOLTAGE
    # ============================================================

    V1 = np.zeros(N)

    # Infer initial RC polarization from first FUDS sample.
    # This is an initial condition, not DST parameter refitting.

    V1[0] = (
        OCV[0]
        + current[0] * R0
        - voltage_measured[0]
    )

    print("\nInitial polarization voltage:", V1[0], "V")


    # ============================================================
    # 12. SIMULATE RC BRANCH
    #
    # V1(k+1) = a*V1(k) + R1*(1-a)*I(k)
    #
    # a = exp(-dt/(R1*C1))
    # ============================================================

    for k in range(N - 1):

        dt = time[k + 1] - time[k]

        a = np.exp(-dt / tau)

        V1[k + 1] = (
            a * V1[k]
            + R1 * (1.0 - a) * current[k]
        )


    # ============================================================
    # 13. PREDICT TERMINAL VOLTAGE
    #
    # CALCE convention:
    # Vmodel = OCV + I*R0 - V1
    # ============================================================

    voltage_model = (
        OCV
        + current * R0
        - V1
    )


    # ============================================================
    # 14. CALCULATE VOLTAGE PREDICTION ERROR
    # ============================================================

    error = voltage_measured - voltage_model

    absolute_error = np.abs(error)

    RMSE = np.sqrt(np.mean(error ** 2))

    MAE = np.mean(absolute_error)

    MAX_ERROR = np.max(absolute_error)

    print("\n" + "-" * 50)

    print("FUDS VALIDATION METRICS")

    print("-" * 50)

    print("RMSE =", RMSE, "V")

    print("MAE =", MAE, "V")

    print("Maximum absolute error =", MAX_ERROR, "V")


    # ============================================================
    # 15. SAVE POINT-BY-POINT RESULTS
    # ============================================================

    results = pd.DataFrame({

        "Elapsed_Time_s": time,

        "Current_A": current,

        "Measured_Voltage_V": voltage_measured,

        "SOC_percent": SOC,

        "OCV_V": OCV,

        "V1_V": V1,

        "Model_Voltage_V": voltage_model,

        "Voltage_Error_V": error,

        "Absolute_Error_V": absolute_error

    })

    csv_name = (
        f"FUDS_{initial_soc}SOC_pointwise_results.csv"
    )

    results.to_csv(
        OUTPUT_FOLDER / csv_name,
        index=False
    )


    # ============================================================
    # 16. PLOT CURRENT VS ELAPSED TIME
    # ============================================================

    plt.figure(figsize=(12, 5))

    plt.plot(time, current, linewidth=0.8)

    plt.xlabel("Elapsed FUDS Time (s)")

    plt.ylabel("Current (A)")

    plt.title(
        f"FUDS Current Profile - {initial_soc}% SOC"
    )

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        OUTPUT_FOLDER /
        f"FUDS_{initial_soc}SOC_current.png",
        dpi=300
    )

    plt.close()


    # ============================================================
    # 17. PLOT MEASURED VOLTAGE VS ELAPSED TIME
    # ============================================================

    plt.figure(figsize=(12, 5))

    plt.plot(
        time,
        voltage_measured,
        color="blue",
        linewidth=0.8
    )

    plt.xlabel("Elapsed FUDS Time (s)")

    plt.ylabel("Measured Voltage (V)")

    plt.title(
        f"Measured FUDS Voltage - {initial_soc}% SOC"
    )

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        OUTPUT_FOLDER /
        f"FUDS_{initial_soc}SOC_measured_voltage.png",
        dpi=300
    )

    plt.close()


    # ============================================================
    # 18. PLOT MEASURED VS MODEL VOLTAGE
    # ============================================================

    plt.figure(figsize=(12, 5))

    plt.plot(
        time,
        voltage_measured,
        label="Measured Voltage",
        linewidth=0.9
    )

    plt.plot(
        time,
        voltage_model,
        label="1-RC Model Voltage",
        linewidth=0.9
    )

    plt.xlabel("Elapsed FUDS Time (s)")

    plt.ylabel("Terminal Voltage (V)")

    plt.title(
        f"FUDS 1-RC Voltage Validation - {initial_soc}% SOC"
    )

    plt.legend()

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        OUTPUT_FOLDER /
        f"FUDS_{initial_soc}SOC_voltage_comparison.png",
        dpi=300
    )

    plt.close()


    # ============================================================
    # 19. PLOT VOLTAGE PREDICTION ERROR
    # ============================================================

    plt.figure(figsize=(12, 5))

    plt.plot(
        time,
        error,
        linewidth=0.8
    )

    plt.axhline(0, linewidth=1)

    plt.xlabel("Elapsed FUDS Time (s)")

    plt.ylabel("Measured - Model Voltage (V)")

    plt.title(
        f"FUDS Voltage Prediction Error - {initial_soc}% SOC"
    )

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        OUTPUT_FOLDER /
        f"FUDS_{initial_soc}SOC_error.png",
        dpi=300
    )

    plt.close()


    # ============================================================
    # 20. RETURN VALIDATION METRICS
    # ============================================================

    metrics = {

        "Initial_SOC_percent": initial_soc,

        "Number_of_samples": N,

        "Duration_s": time[-1],

        "Final_SOC_percent": SOC[-1],

        "R0_ohm": R0,

        "R1_ohm": R1,

        "C1_F": C1,

        "Tau_s": tau,

        "Initial_V1_V": V1[0],

        "RMSE_V": RMSE,

        "MAE_V": MAE,

        "Max_Absolute_Error_V": MAX_ERROR,

        "SOC_outside_OCV_range_samples":
            int(np.sum(outside_range))

    }

    print("\nAll plots and CSV files saved.")

    return metrics


# ================================================================
# 21. RUN BOTH VALIDATION EXPERIMENTS
# ================================================================

if __name__ == "__main__":

    metrics_50 = validate_fuds(50)

    metrics_80 = validate_fuds(80)

    # Combine results
    final_metrics = pd.DataFrame([
        metrics_50,
        metrics_80
    ])

    # Save summary
    final_metrics.to_csv(
        OUTPUT_FOLDER / "FUDS_validation_metrics_summary.csv",
        index=False
    )

    print("\n")
    print("=" * 65)

    print("FINAL FUDS VALIDATION SUMMARY")

    print("=" * 65)

    print(final_metrics.to_string(index=False))

    print("\nAll results saved in:")

    print(OUTPUT_FOLDER)

    print("\nFUDS VALIDATION COMPLETED SUCCESSFULLY!")
