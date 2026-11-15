# Fit 1-RC ECM and Validate-

Fit 1-RC Equivalent Circuit Model & Validate It Using Drive-Cycle Experimental Data

Team Members
1.	Pathivada Jayavardhan — 2026CTE2309 
2.	Vijay Kumar Singh — 2026CTE2664 
3.	Shubham Singh — 2026CTE2814 
Faculty Supervisor:      Prof. Saurabh Saxena
Teaching Assistant (TA):     Haseeba
Abstract: 
                     This project aims to develop a practical first-order battery equivalent-circuit model for an INR 18650-20R lithium-ion cell and evaluate its ability to reproduce terminal-voltage behaviour under a realistic dynamic load profile. Experimental data for Sample 1 at 25 °C are obtained from the Center for Advanced Life Cycle Engineering (CALCE), University of Maryland. Four complementary datasets are used: an initial capacity test, an incremental-current OCV test, a Dynamic Stress Test (DST), and a Federal Urban Driving Schedule (FUDS) test. The capacity test provides the usable capacity required for SOC calculation; the incremental-current OCV test is used to construct the OCV-SOC relationship; the DST provides dynamic voltage-current excitation for identification of the 1-RC model parameters; and FUDS is reserved as an independent validation drive cycle. The final model will be assessed using voltage-tracking metrics such as RMSE, MAE, maximum absolute error, and visual comparison of measured and predicted terminal voltage.

Problem Statement:
                              Given measured current, voltage, and SOC-related experimental data for an INR 18650-20R cell at 25 °C, identify a first-order (1-RC) equivalent-circuit model and validate whether that model can predict the cell terminal voltage under an independent FUDS drive-cycle load.
 Lithium-ion battery voltage changes with state of charge, current, internal resistance, and electrochemical polarization. A simple constant-voltage or purely static battery model cannot adequately represent the transient voltage response produced by rapidly changing charge and discharge currents. For battery-management-system studies, electric-mobility simulations, and drive-cycle analysis, a model is therefore required that is simple enough for real-time simulation but sufficiently accurate to reproduce the dominant dynamic voltage behaviour. 

Project Objectives:
•	Determine the experimental cell capacity from the initial capacity test. 
•	Calculate SOC and obtain the OCV-SOC relationship from the incremental-current OCV data
•	Use DST current-voltage data to find the 1-RC equivalent-circuit parameters R0, R1, and C1. 
•	Implement the model using the measured current as the input and OCV(SOC) as the equilibrium-voltage component. 
•	Run the identified model with the FUDS current profile and compare predicted voltage with measured voltage.
•	Quantify validation accuracy using RMSE, MAE, maximum error, and graphical measured versus-model comparison
